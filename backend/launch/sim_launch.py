from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    # This is a template launch that includes gazebo. Place this file in a ROS2 package's launch/
    # folder and run with `ros2 launch <pkg> sim_launch.py`.
    gazebo_pkg = 'gazebo_ros'
    tb3_pkg = 'turtlebot3_gazebo'

    try:
        gazebo_launch = os.path.join(get_package_share_directory(gazebo_pkg), 'launch', 'gazebo.launch.py')
        world_file = os.path.join(get_package_share_directory(tb3_pkg), 'worlds', 'burger.world')
    except Exception:
        gazebo_launch = None
        world_file = None

    ld = LaunchDescription()

    if gazebo_launch and world_file:
        ld.add_action(
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(gazebo_launch),
                launch_arguments={'world': world_file}.items(),
            )
        )
    return ld
