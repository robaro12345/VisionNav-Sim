"""ROS 2 node that continuously collects runtime context for VisionNav-Sim.

This node only observes existing topics in the workspace and stores the most
recent robot state so the backend can consume a single cached snapshot instead
of querying ROS on every request.
"""

from __future__ import annotations

from math import atan2, sqrt
from typing import Any

import rclpy
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image, LaserScan
from tf2_msgs.msg import TFMessage

from synapse_bringup.context_store import ContextStore
import cv2
from cv_bridge import CvBridge


class ContextNode(Node):
    """Collect the latest robot context from existing ROS topics only."""

    def __init__(self) -> None:
        super().__init__("visionnav_context_node", parameter_overrides=[rclpy.Parameter('use_sim_time', rclpy.Parameter.Type.BOOL, True)])
        self.store = ContextStore()
        self.bridge = CvBridge()
        self.latest_scan_msg: LaserScan | None = None
        self.latest_map_msg: OccupancyGrid | None = None

        # Existing odom topic from the Gazebo DiffDrive plugin.
        self._odom_subscription = self.create_subscription(
            Odometry,
            "/odom",
            self._handle_odom,
            10,
        )

        # Existing TF topic from the Gazebo bridge; used to keep the latest frame activity.
        self._tf_subscription = self.create_subscription(
            TFMessage,
            "/tf",
            self._handle_tf,
            10,
        )

        # Existing LiDAR topic bridged from Gazebo; used for the most recent scan snapshot.
        self._scan_subscription = self.create_subscription(
            LaserScan,
            "/scan",
            self._handle_scan,
            qos_profile_sensor_data,
        )

        # Existing RGB camera topic bridged from Gazebo; used for the latest image timestamp.
        self._image_subscription = self.create_subscription(
            Image,
            "/camera/image_raw",
            self._handle_image,
            qos_profile_sensor_data,
        )

        # Existing map topic published by Nav2/SLAM and shown in RViz.
        self._map_subscription = self.create_subscription(
            OccupancyGrid,
            "/map",
            self._handle_map,
            10,
        )

    def _handle_odom(self, message: Odometry) -> None:
        """Store the latest robot pose and velocity from /odom."""

        pose = message.pose.pose
        twist = message.twist.twist
        speed = sqrt(twist.linear.x**2 + twist.linear.y**2 + twist.linear.z**2)
        self.store.update_pose(
            {
                "position": {
                    "x": pose.position.x,
                    "y": pose.position.y,
                    "z": pose.position.z,
                    "frame_id": message.header.frame_id or "odom",
                },
                "orientation": {
                    "roll": 0.0,
                    "pitch": 0.0,
                    "yaw": atan2(
                        2.0 * (pose.orientation.w * pose.orientation.z + pose.orientation.x * pose.orientation.y),
                        1.0 - 2.0 * (pose.orientation.y**2 + pose.orientation.z**2),
                    ),
                },
                "battery": self.store.get_context().get("battery", 0.0),
                "is_moving": speed > 0.01,
                "velocity_linear": speed,
                "velocity_angular": twist.angular.z,
            }
        )

    def _handle_tf(self, message: TFMessage) -> None:
        """Store a lightweight note that TF data is actively arriving."""

        current_navigation_status = self.store.get_context().get("navigation_status", {})
        self.store.update_nav_status(
            {
                "state": current_navigation_status.get("state", "idle"),
                "status_text": "tf stream active",
                "active_goal": current_navigation_status.get("active_goal", {}),
                "progress": current_navigation_status.get("progress", 0.0),
                "eta_seconds": current_navigation_status.get("eta_seconds"),
                "message": f"latest tf transforms: {len(message.transforms)}",
            }
        )

    def _handle_scan(self, message: LaserScan) -> None:
        """Store a deterministic scan summary from /scan without adding planning logic."""
        self.latest_scan_msg = message

        valid_ranges = [value for value in message.ranges if value > 0.0]
        scan_summary = (
            f"scan frame={message.header.frame_id or 'scan'} "
            f"samples={len(message.ranges)} "
            f"valid={len(valid_ranges)}"
        )
        self.store.update_scene_summary(scan_summary)

    def _handle_image(self, message: Image) -> None:
        """Record that a fresh RGB frame was received from the existing camera topic."""

        self.store.update_scene_summary(
            f"camera frame={message.width}x{message.height} encoding={message.encoding}"
        )
        
        try:
            cv_image = self.bridge.imgmsg_to_cv2(message, desired_encoding='bgr8')
            # Use atomic write to prevent frontend from reading partial file
            final_path = "/home/omkar/Downloads/RobotProject/backend/app/api/camera_frame.jpg"
            temp_path = "/home/omkar/Downloads/RobotProject/backend/app/api/camera_frame_tmp.jpg"
            import os
            cv2.imwrite(temp_path, cv_image)
            os.replace(temp_path, final_path)
        except Exception as e:
            self.get_logger().error(f"Error saving camera frame: {e}")

    def _handle_map(self, message: OccupancyGrid) -> None:
        """Track map progress from the already published /map occupancy grid."""
        self.latest_map_msg = message

        occupied = sum(1 for cell in message.data if cell > 50)
        known = sum(1 for cell in message.data if cell >= 0)
        progress = (occupied / known) if known else 0.0
        self.store.update_map_progress(progress)
        current_navigation_status = self.store.get_context().get("navigation_status", {})
        self.store.update_nav_status(
            {
                "state": current_navigation_status.get("state", "idle"),
                "status_text": "map updated",
                "active_goal": current_navigation_status.get("active_goal", {}),
                "progress": progress,
                "eta_seconds": current_navigation_status.get("eta_seconds"),
                "message": f"map cells known={known} occupied={occupied}",
            }
        )


def main(args: list[str] | None = None) -> None:
    """Run the ROS context node."""

    rclpy.init(args=args)
    node = ContextNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("visionnav_context_node stopped by user")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
