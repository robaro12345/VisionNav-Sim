"""ROS 2 execution engine for VisionNav-Sim.

Executes ActionPlans that have already been validated by the SafetyLayer.
"""

from __future__ import annotations

import logging
import math
import threading
import queue
import cv2
import numpy as np
import base64
import urllib.request
import json
import time
import os
from typing import Any

from geometry_msgs.msg import Twist
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.task import Future

from backend.app.memory.memory_store import MemoryStore
from backend.app.models.types import PlannerResponse, RobotState

logger = logging.getLogger(__name__)


class ExecutorNode(Node):
    """Dedicated ROS 2 node for sending action commands."""

    def __init__(self) -> None:
        import rclpy
        super().__init__("visionnav_executor_node", parameter_overrides=[rclpy.Parameter('use_sim_time', rclpy.Parameter.Type.BOOL, True)])
        
        self.cmd_vel_pub = self.create_publisher(Twist, "/cmd_vel", 10)
        self.nav_to_pose_client = ActionClient(self, NavigateToPose, "navigate_to_pose")
        
        # Track active Nav2 goal for cancellation
        self.active_goal_handle = None


class ROSExecutor:
    """Executes validated planner actions via ROS 2 and Nav2."""

    def __init__(self, memory_store: MemoryStore, node: ExecutorNode, context_node=None) -> None:
        self.memory_store = memory_store
        self.node = node
        self.context_node = context_node
        self.is_exploring = False
        self.explore_thread = None
        self.image_queue = queue.Queue()
        self.exploration_status = "idle"
        self.discovery_worker_thread = threading.Thread(target=self._discovery_worker_loop, daemon=True)
        self.discovery_worker_thread.start()

    def execute_plan(self, session_id: str, planner_response: PlannerResponse) -> None:
        """Execute a validated plan step-by-step."""
        
        memory = self.memory_store.get_session("robot_1", session_id)
        if not memory:
            logger.error(f"Cannot execute plan: session {session_id} not found.")
            return

        logger.info(f"Starting execution for goal: '{planner_response.goal}'")
        memory.start_task(planner_response.goal)
        
        for step in planner_response.plan:
            logger.info(f"Executing step {step.step}: {step.action}")
            success = self._dispatch_action(step.action, step.parameters, memory)
            
            memory.record_navigation({
                "target": step.action,
                "result": "success" if success else "failed"
            })
            
            if not success:
                logger.warning(f"Step {step.step} failed. Aborting plan execution.")
                memory.cancel_task(planner_response.goal)
                return

        logger.info("Plan execution completed successfully.")
        memory.complete_task(planner_response.goal)

    def _dispatch_action(self, action: str, params: dict[str, Any], memory: Any) -> bool:
        """Route the action to the specific ROS handler."""
        
        if action == "explore_environment":
            return self._execute_explore_environment(memory)
        elif action == "navigate_to_pose":
            return self._execute_navigate_to_pose(params)
        elif action == "return_home":
            return self._execute_return_home(memory)
        elif action == "stop_navigation":
            return self._execute_stop_navigation()
        elif action == "cancel_task":
            return self._execute_cancel_task(memory)
        elif action == "navigate_to_object":
            logger.warning("navigate_to_object failed: Object localization is not yet available in v1.")
            return False
        elif action in ["describe_scene", "count_objects", "report_status"]:
            logger.info(f"Action '{action}' is handled independently by the API layer or context store.")
            return True
        elif action in ["search_for_object", "inspect_object", "follow_person"]:
            logger.warning(f"Action '{action}' is not supported yet (stubbed). Failing.")
            return False
        else:
            logger.warning(f"Unknown action: {action}")
            return False

    def _execute_navigate_to_pose(self, params: dict[str, Any], skip_refinement: bool = False) -> bool:
        """Send a goal pose to Nav2."""
        
        x = float(params.get("x", 0.0))
        y = -float(params.get("y", 0.0)) # Invert Y to map LLM lateral perception to ROS (+Y = Left)
        yaw = float(params.get("yaw", 0.0))
        frame_id = params.get("frame_id", "base_link") # Default to base_link for LLMs

        # --- LiDAR Refinement ---
        if not skip_refinement and self.context_node and self.context_node.latest_scan_msg:
            try:
                # 1. Get current robot pose
                context_dict = self.context_node.store.get_context()
                rx, ry, ryaw = 0.0, 0.0, 0.0
                if "robot_pose" in context_dict and "position" in context_dict["robot_pose"]:
                    rx = context_dict["robot_pose"]["position"]["x"]
                    ry = context_dict["robot_pose"]["position"]["y"]
                    ryaw = context_dict["robot_pose"]["orientation"]["yaw"]
                
                # 2. Angle to target depending on frame
                if frame_id == "base_link":
                    theta_robot = math.atan2(y, x)
                    theta_map = ryaw + theta_robot
                else:
                    theta_map = math.atan2(y - ry, x - rx)
                    theta_robot = theta_map - ryaw
                
                # Normalize to [-pi, pi]
                while theta_robot > math.pi: theta_robot -= 2 * math.pi
                while theta_robot < -math.pi: theta_robot += 2 * math.pi
                
                # 3. Find scan index with proper wrapping
                scan = self.context_node.latest_scan_msg
                angle_min = scan.angle_min
                angle_inc = scan.angle_increment
                num_ranges = len(scan.ranges)
                
                index = int(round((theta_robot - angle_min) / angle_inc)) % num_ranges
                
                # 4. Search in a +/- 5 degree window (approx 0.087 rad)
                window_indices = int(0.087 / angle_inc)
                
                valid_ranges = []
                for i in range(-window_indices, window_indices + 1):
                    idx = (index + i) % num_ranges
                    r = scan.ranges[idx]
                    if r > scan.range_min and r < scan.range_max and not math.isinf(r) and not math.isnan(r):
                        valid_ranges.append(r)
                
                if valid_ranges:
                    min_distance = min(valid_ranges)
                    
                    # 5. Refine coordinate (stop 0.5m in front)
                    correction = 0.25
                    stop_distance = max(0.0, min_distance - correction)
                    x = rx + stop_distance * math.cos(theta_map)
                    y = ry + stop_distance * math.sin(theta_map)
                    frame_id = "map"
                    logger.info(f"[LiDAR Refinement] Found obstacle at {min_distance:.2f}m. New target: ({x:.2f}, {y:.2f}) in map frame")
                else:
                    logger.warning("[LiDAR Refinement] No valid scan data in target direction.")
                    
            except Exception as e:
                logger.error(f"[LiDAR Refinement] Error during refinement: {e}")

        if not self.node.nav_to_pose_client.wait_for_server(timeout_sec=2.0):
            logger.error("NavigateToPose action server not available.")
            return False

        goal_msg = NavigateToPose.Goal()
        goal_msg.pose.header.frame_id = frame_id
        goal_msg.pose.header.stamp = self.node.get_clock().now().to_msg()
        
        goal_msg.pose.pose.position.x = float(x)
        goal_msg.pose.pose.position.y = float(y)
        goal_msg.pose.pose.position.z = 0.0
        
        goal_msg.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal_msg.pose.pose.orientation.w = math.cos(yaw / 2.0)

        logger.info(f"Dispatching Nav2 goal: x={x}, y={y}, yaw={yaw}")
        
        send_goal_future = self.node.nav_to_pose_client.send_goal_async(goal_msg)
        
        def goal_response_callback(future: Future) -> None:
            goal_handle = future.result()
            if not goal_handle.accepted:
                logger.info("Goal rejected by Nav2.")
                return
            
            logger.info("Goal accepted by Nav2.")
            self.node.active_goal_handle = goal_handle

        send_goal_future.add_done_callback(goal_response_callback)
        return True

    def _execute_return_home(self, memory: Any) -> bool:
        """Return to the recorded session start pose."""
        
        context = memory.get_context()
        start_pose: RobotState | None = context.start_pose
        
        if not start_pose:
            logger.warning("No start_pose found in memory. Cannot return home. Failing.")
            return False

        params = {
            "x": start_pose.position.x, 
            "y": start_pose.position.y,
            "yaw": start_pose.orientation.yaw,
            "frame_id": start_pose.position.frame_id
        }
            
        logger.info(f"Returning home to {params}")
        return self._execute_navigate_to_pose(params)

    def _execute_stop_navigation(self) -> bool:
        """Halt the robot immediately via cmd_vel and Nav2 cancellation."""
        self.is_exploring = False
        self.exploration_status = "idle"
        
        if self.node.active_goal_handle is not None:
            logger.info("Cancelling active Nav2 goal...")
            self.node.active_goal_handle.cancel_goal_async()
            self.node.active_goal_handle = None
            
        msg = Twist()
        self.node.cmd_vel_pub.publish(msg)
        logger.info("Published stop command to /cmd_vel")
        
        return True

    def _execute_cancel_task(self, memory: Any) -> bool:
        """Cancel the current task."""
        
        logger.info("Task cancellation requested.")
        return self._execute_stop_navigation()

    def _execute_explore_environment(self, memory: Any) -> bool:
        if self.is_exploring:
            logger.info("Already exploring.")
            return True
            
        self.is_exploring = True
        self.exploration_status = "active"
        self.explore_thread = threading.Thread(target=self._exploration_loop, args=(memory,), daemon=True)
        self.explore_thread.start()
        logger.info("Started continuous frontier exploration.")
        return True

    def _exploration_loop(self, memory: Any) -> None:
        last_snapshot_pose = None
        while self.is_exploring:
            try:
                if not self.context_node or not self.context_node.latest_map_msg:
                    time.sleep(1.0)
                    continue
                    
                context_dict = self.context_node.store.get_context()
                if "robot_pose" in context_dict and "position" in context_dict["robot_pose"]:
                    x = context_dict["robot_pose"]["position"]["x"]
                    y = context_dict["robot_pose"]["position"]["y"]
                    yaw = context_dict["robot_pose"]["orientation"]["yaw"]
                    
                    if last_snapshot_pose is None:
                        self._queue_snapshot()
                        last_snapshot_pose = (x, y, yaw)
                    else:
                        dx = x - last_snapshot_pose[0]
                        dy = y - last_snapshot_pose[1]
                        dyaw = yaw - last_snapshot_pose[2]
                        while dyaw > math.pi: dyaw -= 2 * math.pi
                        while dyaw < -math.pi: dyaw += 2 * math.pi
                        
                        dist = math.sqrt(dx*dx + dy*dy)
                        if dist > 1.0 or abs(dyaw) > 0.785: # 1 meter or 45 degrees
                            self._queue_snapshot()
                            last_snapshot_pose = (x, y, yaw)
                            
                map_msg = self.context_node.latest_map_msg
                width = map_msg.info.width
                height = map_msg.info.height
                res = map_msg.info.resolution
                ox = map_msg.info.origin.position.x
                oy = map_msg.info.origin.position.y
                
                data = np.array(map_msg.data, dtype=np.int8).reshape((height, width))
                
                free_space = np.logical_and(data >= 0, data < 50).astype(np.uint8) * 255
                unknown_space = (data == -1).astype(np.uint8) * 255
                
                kernel = np.ones((3,3), np.uint8)
                dilated_unknown = cv2.dilate(unknown_space, kernel, iterations=1)
                frontiers = cv2.bitwise_and(free_space, dilated_unknown)
                
                contours, _ = cv2.findContours(frontiers, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if contours:
                    # Find the longest frontier line
                    largest_contour = max(contours, key=len)
                    if len(largest_contour) > 5:
                        # Pick a point directly ON the frontier line (middle of the contour array)
                        mid_idx = len(largest_contour) // 2
                        cx = largest_contour[mid_idx][0][0]
                        cy = largest_contour[mid_idx][0][1]
                        
                        target_x = ox + cx * res
                        target_y = oy + cy * res
                        
                        logger.info(f"[Frontier Explorer] Found new frontier goal at ({target_x:.2f}, {target_y:.2f})")
                        self._execute_navigate_to_pose({"x": target_x, "y": target_y, "frame_id": "map"}, skip_refinement=True)
                    else:
                        logger.info("[Frontier Explorer] Frontiers too small, map might be complete.")
                        self.exploration_status = "completed"
                else:
                    logger.info("[Frontier Explorer] No frontiers found. Map complete!")
                    self.exploration_status = "completed"
                    
            except Exception as e:
                logger.error(f"[Frontier Explorer] Error: {e}")
                
            time.sleep(5.0)

    def _queue_snapshot(self) -> None:
        image_path = "/home/omkar/RobotProject/backend/app/api/camera_frame.jpg"
        if os.path.exists(image_path):
            try:
                with open(image_path, "rb") as f:
                    image_data = f.read()
                    self.image_queue.put(image_data)
                    logger.info("[Frontier Explorer] Snapshot added to queue.")
            except Exception as e:
                logger.error(f"[Frontier Explorer] Error reading snapshot: {e}")

    def _discovery_worker_loop(self) -> None:
        model_name = os.getenv("OLLAMA_MODEL", "gemma4:e4b")
        endpoint = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434").rstrip("/")
        url = f"{endpoint}/api/generate"
        
        while True:
            image_data = self.image_queue.get()
            try:
                base64_image = base64.b64encode(image_data).decode("utf-8")
                prompt = (
                    "Analyze this image and list any distinct objects and their characteristics. "
                    "Output ONLY a JSON array of objects, e.g. [{\"label\": \"box\", \"characteristics\": \"red, small\"}]. "
                    "Do NOT output markdown blocks or any other text."
                )
                request_body = {
                    "model": model_name,
                    "prompt": prompt,
                    "format": "json",
                    "stream": False,
                    "images": [base64_image],
                    "options": {"temperature": 0.1}
                }
                
                req = urllib.request.Request(
                    url,
                    data=json.dumps(request_body).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                
                with urllib.request.urlopen(req, timeout=180) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    response_text = resp_data.get("response", "").strip()
                    
                    # Clean markdown code blocks if present
                    if response_text.startswith("```"):
                        lines = response_text.splitlines()
                        if lines[0].startswith("```json") or lines[0].startswith("```"):
                            lines = lines[1:]
                        if lines and lines[-1].strip() == "```":
                            lines = lines[:-1]
                        response_text = "\\n".join(lines).strip()
                    
                    if response_text:
                        logger.info(f"[Object Discovery] Found new objects: {response_text}")
                        # In a real app we'd append this to memory store
                        
            except Exception as e:
                logger.error(f"[Object Discovery] Error: {e}")
            finally:
                self.image_queue.task_done()
