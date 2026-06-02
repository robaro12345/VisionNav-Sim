"""ROS 2 execution engine for VisionNav-Sim.

Executes ActionPlans that have already been validated by the SafetyLayer.
"""

from __future__ import annotations

import logging
import math
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
        
        if action == "navigate_to_pose":
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

    def _execute_navigate_to_pose(self, params: dict[str, Any]) -> bool:
        """Send a goal pose to Nav2."""
        
        x = float(params.get("x", 0.0))
        y = float(params.get("y", 0.0))
        yaw = float(params.get("yaw", 0.0))
        frame_id = params.get("frame_id", "base_link") # Default to base_link for LLMs

        # --- LiDAR Refinement ---
        if self.context_node and self.context_node.latest_scan_msg:
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
                    stop_distance = max(0.0, min_distance - 0.5)
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
