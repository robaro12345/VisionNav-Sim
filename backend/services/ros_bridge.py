"""ROS2 NavBridge implementation (safe if ROS2 not installed).

This module implements a small runtime-safe bridge to ROS2 that:
- lazily imports `rclpy` and message types when needed
- exposes `start()`, `stop()`, and `send_goal()` helpers
- subscribes to `/camera/image_raw` and `/scan` and stores last messages

Note: running methods requires a ROS2 environment (Jazzy) and the
appropriate message packages (`geometry_msgs`, `sensor_msgs`, etc.).
"""
from typing import Optional, Any, Dict
import threading
import time


def _image_to_bgr_array(msg):
    try:
        import numpy as np
    except Exception:
        return None

    encoding = getattr(msg, "encoding", "").lower()
    height = int(getattr(msg, "height", 0) or 0)
    width = int(getattr(msg, "width", 0) or 0)
    step = int(getattr(msg, "step", 0) or 0)
    data = getattr(msg, "data", b"")

    if not height or not width or not data:
        return None

    buffer = np.frombuffer(data, dtype=np.uint8)

    if encoding in {"rgb8", "bgr8"}:
        channels = 3
    elif encoding in {"rgba8", "bgra8"}:
        channels = 4
    elif encoding in {"mono8", "8uc1"}:
        channels = 1
    else:
        return None

    expected = height * (step or width * channels)
    if buffer.size < expected:
        return None

    array = buffer[: expected].reshape((height, step or width * channels))

    if channels == 1:
        image = array[:, :width].reshape((height, width))
        image = np.stack([image, image, image], axis=-1)
    else:
        image = array[:, : width * channels].reshape((height, width, channels))
        if encoding == "rgb8":
            image = image[:, :, ::-1]
        elif encoding == "rgba8":
            image = image[:, :, [2, 1, 0, 3]][:, :, :3]
        elif encoding == "bgra8":
            image = image[:, :, :3]

    return image.copy()


class RosBridge:
    def __init__(self, node_name: str = "nav_bridge") -> None:
        self.node_name = node_name
        self.node = None
        self._rclpy = None
        self._msg_types = {}
        self.publisher = None
        self.navigate_client = None
        self.cmd_vel_publisher = None
        self.image_sub = None
        self.scan_sub = None
        self.spin_thread: Optional[threading.Thread] = None
        self.is_running = False
        self.last_image = None
        self.last_image_msg = None
        self.last_scan = None
        self.last_scan_msg = None

    def _import_ros(self):
        try:
            import rclpy
            from rclpy.node import Node
            from rclpy.qos import qos_profile_sensor_data
            from rclpy.action import ActionClient
            from geometry_msgs.msg import PoseStamped, Pose, Point, Quaternion, Twist
            from nav2_msgs.action import NavigateToPose
            from sensor_msgs.msg import Image, LaserScan
            from std_msgs.msg import Header
        except Exception as e:  # pragma: no cover - environment specific
            raise RuntimeError(
                "ROS2 packages not available. Ensure ROS2 Jazzy and message packages are installed: "
                + str(e)
            )

        self._rclpy = rclpy
        self._msg_types = {
            "Node": Node,
            "ActionClient": ActionClient,
            "PoseStamped": PoseStamped,
            "Pose": Pose,
            "Point": Point,
            "Quaternion": Quaternion,
            "Twist": Twist,
            "NavigateToPose": NavigateToPose,
            "Image": Image,
            "LaserScan": LaserScan,
            "Header": Header,
            "qos_profile_sensor_data": qos_profile_sensor_data,
        }
        return self._rclpy, self._msg_types

    def start(self) -> None:
        """Initialize rclpy, create node, publisher and subscriptions, and start spin thread."""
        if self.is_running:
            return

        rclpy, msgs = self._import_ros()

        # Initialize rclpy (safe to call multiple times)
        try:
            rclpy.init()
        except Exception:
            # rclpy.init() may have already been called by another component
            pass

        Node = msgs["Node"]
        ActionClient = msgs["ActionClient"]
        PoseStamped = msgs["PoseStamped"]
        NavigateToPose = msgs["NavigateToPose"]
        Twist = msgs["Twist"]
        qos_sensor = msgs["qos_profile_sensor_data"]

        # Create node and basic publisher/subscribers
        self.node = Node(self.node_name)
        self.publisher = self.node.create_publisher(PoseStamped, "/goal_pose", 10)
        self.navigate_client = ActionClient(self.node, NavigateToPose, "/navigate_to_pose")
        self.cmd_vel_publisher = self.node.create_publisher(Twist, "/cmd_vel", 10)
        Image = msgs["Image"]
        LaserScan = msgs["LaserScan"]

        # simple callbacks store last message on the instance
        def _image_cb(msg: Image) -> None:
            self.last_image_msg = msg
            self.last_image = _image_to_bgr_array(msg)

        def _scan_cb(msg: LaserScan) -> None:
            self.last_scan_msg = msg
            self.last_scan = msg

        # create subscriptions with sensor qos
        try:
            self.image_sub = self.node.create_subscription(Image, "/camera/image_raw", _image_cb, qos_sensor)
        except Exception:
            # subscription optional in non-sim environments
            self.image_sub = None

        try:
            self.scan_sub = self.node.create_subscription(LaserScan, "/scan", _scan_cb, qos_sensor)
        except Exception:
            self.scan_sub = None

        self.is_running = True

        # start a background thread to spin the node
        def _spin_thread():
            try:
                while self.is_running and rclpy.ok():
                    rclpy.spin_once(self.node, timeout_sec=0.1)
                    time.sleep(0.01)
            except Exception:
                pass

        self.spin_thread = threading.Thread(target=_spin_thread, daemon=True)
        self.spin_thread.start()

    def _build_pose_stamped(self, pose_stamped: Any):
        PoseStamped = self._msg_types.get("PoseStamped")
        Point = self._msg_types.get("Point")
        Quaternion = self._msg_types.get("Quaternion")
        Header = self._msg_types.get("Header")

        if PoseStamped is None:
            raise RuntimeError("ROS2 message types not loaded")

        if isinstance(pose_stamped, PoseStamped):
            return pose_stamped

        if not isinstance(pose_stamped, dict):
            raise TypeError("send_goal expects a PoseStamped or dict")

        msg = PoseStamped()
        header = Header()
        header.stamp = self.node.get_clock().now().to_msg()
        header.frame_id = pose_stamped.get("frame_id", "map")
        msg.header = header

        pos = pose_stamped.get("position", {})
        ori = pose_stamped.get("orientation", {})

        msg.pose.position = Point(x=pos.get("x", 0.0), y=pos.get("y", 0.0), z=pos.get("z", 0.0))
        msg.pose.orientation = Quaternion(x=ori.get("x", 0.0), y=ori.get("y", 0.0), z=ori.get("z", 0.0), w=ori.get("w", 1.0))
        return msg

    def _wait_for_future(self, future, timeout: float = 5.0):
        deadline = time.time() + timeout
        while not future.done() and time.time() < deadline:
            time.sleep(0.05)
        if not future.done():
            raise TimeoutError("Timed out waiting for ROS2 future")
        return future.result()

    def send_goal(self, pose_stamped: Any) -> None:
        """Send a navigation goal to Nav2.

        Accepts either a ROS `PoseStamped` instance or a dict with keys:
        `{ 'frame_id': str, 'position': {'x','y','z'}, 'orientation': {'x','y','z','w'} }`.
        """
        if self.publisher is None and self.navigate_client is None:
            raise RuntimeError("ROS2 bridge not started. Call start() before send_goal().")

        msg = self._build_pose_stamped(pose_stamped)

        if self.navigate_client is not None:
            if not self.navigate_client.wait_for_server(timeout_sec=5.0):
                raise RuntimeError("Nav2 NavigateToPose action server is not available")

            NavigateToPose = self._msg_types.get("NavigateToPose")
            if NavigateToPose is None:
                raise RuntimeError("ROS2 message types not loaded")

            goal = NavigateToPose.Goal()
            goal.pose = msg
            future = self.navigate_client.send_goal_async(goal)
            goal_handle = self._wait_for_future(future, timeout=5.0)
            if not getattr(goal_handle, "accepted", False):
                raise RuntimeError("Nav2 rejected the navigation goal")
            return

        self.publisher.publish(msg)

    def send_velocity(self, linear_x: float = 0.0, angular_z: float = 0.0) -> None:
        """Publish a simple velocity command to /cmd_vel."""
        if self.cmd_vel_publisher is None:
            raise RuntimeError("ROS2 bridge not started. Call start() before send_velocity().")

        Twist = self._msg_types.get("Twist")
        if Twist is None:
            raise RuntimeError("ROS2 message types not loaded")

        msg = Twist()
        msg.linear.x = float(linear_x)
        msg.linear.y = 0.0
        msg.linear.z = 0.0
        msg.angular.x = 0.0
        msg.angular.y = 0.0
        msg.angular.z = float(angular_z)
        self.cmd_vel_publisher.publish(msg)

    def stop(self) -> None:
        """Stop spinning, destroy node and shutdown rclpy."""
        if not self.is_running:
            return

        self.is_running = False
        if self.spin_thread is not None:
            self.spin_thread.join(timeout=1.0)

        try:
            if self.node is not None:
                self.node.destroy_node()
        except Exception:
            pass

        try:
            if self._rclpy is not None:
                self._rclpy.shutdown()
        except Exception:
            pass

        self.node = None
        self.publisher = None
        self.navigate_client = None
        self.cmd_vel_publisher = None
        self.spin_thread = None

    def snapshot_sensors(self) -> Dict[str, Any]:
        """Return the latest ROS sensor data in a graph-friendly shape."""
        sensors: Dict[str, Any] = {}

        if self.last_image is not None:
            sensors["image"] = self.last_image
        elif self.last_image_msg is not None:
            sensors["image_msg"] = self.last_image_msg

        if self.last_scan is not None:
            scan = self.last_scan
            ranges = list(getattr(scan, "ranges", []))
            sensors["scan"] = {
                "ranges": ranges,
                "angle_min": float(getattr(scan, "angle_min", 0.0)),
                "angle_max": float(getattr(scan, "angle_max", 0.0)),
                "angle_increment": float(getattr(scan, "angle_increment", 0.0)),
            }
        elif self.last_scan_msg is not None:
            scan = self.last_scan_msg
            ranges = list(getattr(scan, "ranges", []))
            sensors["scan"] = {
                "ranges": ranges,
                "angle_min": float(getattr(scan, "angle_min", 0.0)),
                "angle_max": float(getattr(scan, "angle_max", 0.0)),
                "angle_increment": float(getattr(scan, "angle_increment", 0.0)),
            }

        return sensors


def example_usage():
    """Small example showing how to start the bridge and publish a goal.

    This function is safe to import even if ROS2 isn't installed; executing it
    requires a running ROS2 environment.
    """
    bridge = RosBridge()
    bridge.start()
    try:
        goal = {
            "frame_id": "map",
            "position": {"x": 1.0, "y": 0.5, "z": 0.0},
            "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        }
        bridge.send_goal(goal)
        time.sleep(0.5)
    finally:
        bridge.stop()


if __name__ == "__main__":
    try:
        example_usage()
    except RuntimeError as e:
        print("ROS2 not available:", e)
