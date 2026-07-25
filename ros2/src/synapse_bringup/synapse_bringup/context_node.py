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
import cv2
from cv_bridge import CvBridge
from tf2_ros import Buffer, TransformListener

from synapse_bringup.context_store import ContextStore


class ContextNode(Node):
    """Collect the latest robot context from existing ROS topics only."""

    def __init__(self) -> None:
        super().__init__("visionnav_context_node", parameter_overrides=[rclpy.Parameter('use_sim_time', rclpy.Parameter.Type.BOOL, True)])
        self.store = ContextStore()
        self.latest_scan_msg: LaserScan | None = None
        self.latest_map_msg: OccupancyGrid | None = None
        self.bridge = CvBridge()
        self.latest_image_jpeg: bytes | None = None

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        
        self.pose_timer = self.create_timer(0.1, self._update_pose_from_tf)

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
        """Store the latest robot velocity from /odom."""
        twist = message.twist.twist
        speed = sqrt(twist.linear.x**2 + twist.linear.y**2 + twist.linear.z**2)
        
        # Only update velocities, position is handled by TF map->base_link
        current_pose = self.store.get_context().get("robot_pose", {})
        if current_pose:
            current_pose["is_moving"] = speed > 0.01
            current_pose["velocity_linear"] = speed
            current_pose["velocity_angular"] = twist.angular.z
            self.store.update_pose(current_pose)

    def _update_pose_from_tf(self) -> None:
        """Continuously update robot pose in the map frame."""
        try:
            now = rclpy.time.Time()
            trans = self.tf_buffer.lookup_transform("map", "base_link", now)
            
            x = trans.transform.translation.x
            y = trans.transform.translation.y
            z = trans.transform.translation.z
            
            q = trans.transform.rotation
            yaw = atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y**2 + q.z**2))
            
            current_pose = self.store.get_context().get("robot_pose", {})
            self.store.update_pose(
                {
                    "position": {
                        "x": x,
                        "y": y,
                        "z": z,
                        "frame_id": "map",
                    },
                    "orientation": {
                        "roll": 0.0,
                        "pitch": 0.0,
                        "yaw": yaw,
                    },
                    "battery": self.store.get_context().get("battery", 100.0),
                    "is_moving": current_pose.get("is_moving", False),
                    "velocity_linear": current_pose.get("velocity_linear", 0.0),
                    "velocity_angular": current_pose.get("velocity_angular", 0.0),
                }
            )
        except Exception:
            pass

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
            success, buffer = cv2.imencode('.jpg', cv_image)
            if success:
                self.latest_image_jpeg = buffer.tobytes()
        except Exception as e:
            self.get_logger().error(f"Error converting image: {e}")

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
