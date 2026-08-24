"""ROS 2 execution engine for VisionNav-Sim.

Executes ActionPlans that have already been validated by the SafetyLayer.
"""

from __future__ import annotations

import logging
import math
import threading
import json
import time
import os
import subprocess
import yaml
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
        self.exploration_status = "idle"

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
            success = self._dispatch_action(step.action, step.parameters, memory, goal=planner_response.goal)
            
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

    def _dispatch_action(self, action: str, params: dict[str, Any], memory: Any, goal: str = "") -> bool:
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
            return self._execute_navigate_to_object(params, memory, goal=goal)
        elif action in ["describe_scene", "count_objects", "report_status"]:
            logger.info(f"Action '{action}' is handled independently by the API layer or context store.")
            return True
        elif action in ["search_for_object", "inspect_object", "follow_person"]:
            logger.warning(f"Action '{action}' is not supported yet (stubbed). Failing.")
            return False
        else:
            logger.warning(f"Unknown action: {action}")
            return False

    def _get_map_metadata(self) -> tuple[float, float, float]:
        """Returns (origin_x, origin_y, resolution) from map.yaml or defaults."""
        map_dir = "/home/omkar/Downloads/RobotProject/map"
        map_yaml_path = os.path.join(map_dir, "map.yaml")
        origin_x, origin_y, resolution = -7.948, -9.508, 0.05
        if os.path.exists(map_yaml_path):
            try:
                with open(map_yaml_path, "r") as f:
                    data = yaml.safe_load(f)
                origin = data.get("origin", [origin_x, origin_y, 0])
                origin_x = float(origin[0])
                origin_y = float(origin[1])
                resolution = float(data.get("resolution", resolution))
            except Exception as e:
                logger.warning(f"Error loading map.yaml metadata: {e}")
        return origin_x, origin_y, resolution

    def _get_semantic_objects(self) -> list[dict[str, Any]]:
        """Returns list of semantic objects from context node or semantic_map.json."""
        if self.context_node:
            context_dict = self.context_node.store.get_context()
            if "semantic_objects" in context_dict and context_dict["semantic_objects"]:
                return context_dict["semantic_objects"]

        map_dir = "/home/omkar/Downloads/RobotProject/map"
        semantic_map_path = os.path.join(map_dir, "semantic_map.json")
        if os.path.exists(semantic_map_path):
            try:
                with open(semantic_map_path, "r") as f:
                    data = json.load(f)
                return data.get("objects", [])
            except Exception as e:
                logger.warning(f"Error loading semantic_map.json: {e}")
        return []

    def _execute_navigate_to_object(self, params: dict[str, Any], memory: Any, goal: str = "") -> bool:
        """Find the target object in the semantic map and navigate to it."""
        import re
        target = params.get("object_name") or params.get("label") or ""
        
        # Combine target label and overall goal text (e.g. "cube" + "Navigate to the pink cube.")
        full_query = f"{target} {goal}".lower()
        cleaned_query = re.sub(r"[^a-zA-Z0-9\s]", " ", full_query)
        stopwords = {"to", "the", "a", "an", "at", "in", "on", "navigate", "go", "move", "drive", "reach", "find", "object", "please"}
        tokens = [t for t in cleaned_query.split() if t and t not in stopwords]

        objects = self._get_semantic_objects()
        if not objects:
            logger.warning(f"No semantic objects available to locate '{target}'.")
            return False

        best_match = None
        best_score = -1.0

        for obj in objects:
            name = str(obj.get("name", "")).lower()
            desc = str(obj.get("description", "")).lower()
            
            score = 0.0
            target_lower = target.lower().strip()
            
            # Base name match
            if target_lower and target_lower == name:
                score += 5.0
            elif target_lower and target_lower in name:
                score += 3.0

            # Match modifier tokens (colors, descriptions e.g. "pink", "yellow", "cube")
            for token in tokens:
                if token == name or token in name:
                    score += 4.0
                if token in desc:
                    score += 5.0 # High weight for color and descriptive keywords

            # Exact phrase match in description
            if target_lower and len(target_lower) > 3 and target_lower in desc:
                score += 6.0

            if score > best_score and score > 0:
                best_score = score
                best_match = obj

        if not best_match:
            logger.warning(f"Could not find any semantic object matching '{target}' (goal: '{goal}').")
            return False

        obj_name = best_match.get("name", "object")
        centroid = best_match.get("centroid")
        if not centroid or len(centroid) < 2:
            logger.error(f"Matched object '{obj_name}' has invalid centroid: {centroid}")
            return False

        # Centroid is stored as [row, col] in grid coordinates
        row, col = float(centroid[0]), float(centroid[1])
        origin_x, origin_y, resolution = self._get_map_metadata()
        
        # Convert grid (row, col) to map frame (x, y)
        world_x = origin_x + (col + 0.5) * resolution
        world_y = origin_y + (row + 0.5) * resolution

        logger.info(
            f"Found target '{target}' -> '{obj_name}' (ID: {best_match.get('id')}) at map coords ({world_x:.2f}, {world_y:.2f})"
        )

        # Get current robot pose
        rx, ry, ryaw = 0.0, 0.0, 0.0
        if self.context_node:
            context_dict = self.context_node.store.get_context()
            if "robot_pose" in context_dict and "position" in context_dict["robot_pose"]:
                rx = context_dict["robot_pose"]["position"]["x"]
                ry = context_dict["robot_pose"]["position"]["y"]
                ryaw = context_dict["robot_pose"]["orientation"]["yaw"]

        # Calculate approach waypoint at a safe standoff distance (1.0m)
        standoff = 1.0
        dx = world_x - rx
        dy = world_y - ry
        dist = math.hypot(dx, dy)

        if dist > standoff:
            ux = dx / dist
            uy = dy / dist
            goal_x = world_x - standoff * ux
            goal_y = world_y - standoff * uy
        else:
            goal_x = rx
            goal_y = ry

        goal_yaw = math.atan2(dy, dx)

        nav_params = {
            "x": goal_x,
            "y": goal_y,
            "yaw": goal_yaw,
            "frame_id": "map"
        }

        logger.info(f"Navigating to object '{obj_name}' waypoint: x={goal_x:.2f}, y={goal_y:.2f}, yaw={goal_yaw:.2f}")
        return self._execute_navigate_to_pose(nav_params)

    def _execute_navigate_to_pose(self, params: dict[str, Any], skip_refinement: bool = False) -> bool:
        """Send a goal pose to Nav2."""
        
        frame_id = params.get("frame_id", "base_link") # Default to base_link for LLMs
        x = float(params.get("x", 0.0))
        y = float(params.get("y", 0.0))
        yaw = float(params.get("yaw", 0.0))

        rx, ry, ryaw = 0.0, 0.0, 0.0
        if self.context_node:
            context_dict = self.context_node.store.get_context()
            if "robot_pose" in context_dict and "position" in context_dict["robot_pose"]:
                rx = context_dict["robot_pose"]["position"]["x"]
                ry = context_dict["robot_pose"]["position"]["y"]
                ryaw = context_dict["robot_pose"]["orientation"]["yaw"]

        # 1. Transform to map frame if needed
        if frame_id == "base_link":
            # Invert Y to map LLM lateral perception (+Y = right) to ROS (+Y = left)
            y = -y
            x_map = rx + x * math.cos(ryaw) - y * math.sin(ryaw)
            y_map = ry + x * math.sin(ryaw) + y * math.cos(ryaw)
            yaw_map = ryaw + yaw
            x, y, yaw = x_map, y_map, yaw_map
            frame_id = "map"

        # 2. LiDAR Refinement has been removed to allow Nav2 to handle obstacle avoidance natively.

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
        
        # Wait for goal to be accepted
        while not send_goal_future.done():
            time.sleep(0.1)
            
        goal_handle = send_goal_future.result()
        if not goal_handle.accepted:
            logger.warning("Goal rejected by Nav2.")
            return False
            
        logger.info("Goal accepted by Nav2, waiting for completion...")
        self.node.active_goal_handle = goal_handle
        
        # Wait for the action to complete
        result_future = goal_handle.get_result_async()
        while not result_future.done():
            time.sleep(0.1)
            
        result = result_future.result()
        status = result.status
        logger.info(f"Nav2 goal finished with status: {status}")
        self.node.active_goal_handle = None
        
        return status == 4 # 4 == SUCCEEDED

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
        self.explore_thread = threading.Thread(target=self._run_mapping_pipeline, daemon=True)
        self.explore_thread.start()
        logger.info("Started external mapping pipeline.")
        return True

    def _run_mapping_pipeline(self) -> None:
        """Runs the external frontier exploration and semantic mapping pipeline."""
        
        # Load map directory from configuration
        install_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../..'))
        config_path = os.path.join(install_dir, 'config', 'paths.yaml')
        map_dir = "/home/omkar/Downloads/RobotProject/map" # fallback
        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
            map_dir = config.get("map_dir", map_dir)
        except Exception as e:
            logger.warning(f"Could not load paths.yaml, using default map_dir: {e}")
            
        map_yaml_path = os.path.join(map_dir, "map.yaml")
        semantic_map_path = os.path.join(map_dir, "semantic_map.json")
        
        if os.path.exists(map_yaml_path) and os.path.exists(semantic_map_path):
            logger.info("Map and semantic map already exist. Skipping exploration.")
            self.is_exploring = False
            self.exploration_status = "completed"
            return
            
        logger.info("Map not found. Starting mapping pipeline...")
        try:
            logger.info("1/3: Running Frontier Exploration...")
            subprocess.run(["ros2", "run", "fronter_exploration", "main_node"], check=True)
            
            logger.info("2/3: Saving Occupancy Map...")
            os.makedirs(map_dir, exist_ok=True)
            map_file_prefix = os.path.join(map_dir, "map")
            subprocess.run(["ros2", "run", "nav2_map_server", "map_saver_cli", "-f", map_file_prefix], check=True)
            
            logger.info("3/3: Running Semantic Mapper...")
            subprocess.run(["ros2", "run", "semantic_mapper", "main_node", "--ros-args", "-p", f"map_dir:={map_dir}"], check=True)
            
            logger.info("Mapping pipeline completed successfully.")
            self.exploration_status = "completed"
        except subprocess.CalledProcessError as e:
            logger.error(f"Mapping pipeline failed at step: {e.cmd}")
            self.exploration_status = "failed"
        except Exception as e:
            logger.error(f"Error in mapping pipeline: {e}")
            self.exploration_status = "failed"
        finally:
            self.is_exploring = False
