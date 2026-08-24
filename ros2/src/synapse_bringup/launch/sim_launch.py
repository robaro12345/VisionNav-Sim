import os
import yaml

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource

from launch_ros.actions import Node

from launch.actions import ExecuteProcess

def generate_launch_description():
    gz_pkg = 'ros_gz_sim'
    tb3_pkg = 'nav2_minimal_tb3_sim'
    nav2_pkg = 'nav2_bringup'
    rviz_pkg = 'synapse_bringup'

    tb3_share = get_package_share_directory(tb3_pkg)

    try:
        gz_launch = os.path.join(
            get_package_share_directory(gz_pkg),
            'launch',
            'gz_sim.launch.py'
        )

        spawn_launch = os.path.join(
            tb3_share,
            'launch',
            'spawn_tb3.launch.py'
        )

        nav2_launch = os.path.join(
            get_package_share_directory(nav2_pkg),
            'launch',
            'bringup_launch.py'
        )

        rviz_config = os.path.join(
            get_package_share_directory(rviz_pkg),
            'rviz',
            'nav2_sim.rviz'
        )

        nav2_params_file = os.path.join(
            get_package_share_directory(nav2_pkg),
            'params',
            'nav2_params.yaml'
        )

        world_file = os.path.join(
            get_package_share_directory(rviz_pkg),
            'worlds',
            'test_world.sdf'
        )

        robot_description_path = os.path.join(
            get_package_share_directory('synapse_bringup'),
            'urdf',
            'turtlebot3_waffle.urdf'
        )

        robot_sdf = os.path.join(
            get_package_share_directory('synapse_bringup'),
            'urdf',
            'gz_waffle_rgb.sdf.xacro'
        )

        

        with open(robot_description_path, 'r', encoding='utf-8') as f:
            robot_description = f.read()

    except Exception as e:
        print(f"Launch setup failed: {e}")
        return LaunchDescription()

    ld = LaunchDescription()

    #
    # Gazebo
    #
    ld.add_action(
        ExecuteProcess(
            cmd=[
                'gz',
                'sim',
                '-r',
                world_file
            ],
            output='screen'
        )
    )

    #
    # Robot State Publisher
    #
    ld.add_action(
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[
                {'use_sim_time': True},
                {'robot_description': robot_description},
            ],
        )
    )

    #
    # Spawn TurtleBot3
    #
    ld.add_action(
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(spawn_launch),
            launch_arguments={
                'robot_name': 'turtlebot3_waffle',
                'robot_sdf': robot_sdf,
                'x_pose': '-2.00',
                'y_pose': '-0.50',
                'z_pose': '0.01',
                'roll': '0.00',
                'pitch': '0.00',
                'yaw': '0.00',
            }.items(),
        )
    )
    #
    # Bridge activation
    #
    ld.add_action(
        Node(
            package='ros_gz_bridge',
            executable='parameter_bridge',
            name='camera_bridge',
            output='screen',
            arguments=[
                '/camera/image_raw@sensor_msgs/msg/Image@gz.msgs.Image'
            ],
        )
    )
    #
    # Nav2 + SLAM
    #
    # Locate RobotProject root by traversing up from the install directory
    install_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../../..'))
    config_path = os.path.join(install_dir, 'config', 'paths.yaml')
    use_slam = 'True'
    map_arg = ''
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        map_dir = config.get("map_dir", "/home/omkar/Downloads/RobotProject/map")
        map_yaml_path = os.path.join(map_dir, "map.yaml")
        if os.path.exists(map_yaml_path):
            use_slam = 'False'
            map_arg = map_yaml_path
    except Exception as e:
        print(f"Could not load paths.yaml: {e}")

    nav2_args = {
        'slam': use_slam,
        'use_localization': 'True',
        'use_sim_time': 'true',
        'autostart': 'true',
        'use_composition': 'False',
        'use_respawn': 'False',
        'params_file': nav2_params_file,
    }
    if map_arg:
        nav2_args['map'] = map_arg

    ld.add_action(
        TimerAction(
            period=20.0,
            actions=[
                IncludeLaunchDescription(
                    PythonLaunchDescriptionSource(nav2_launch),
                    launch_arguments=nav2_args.items(),
                )
            ],
        )
    )

    #
    # Auto-seed initial pose for AMCL if using a static map
    #
    if use_slam == 'False':
        initial_pose_msg = (
            '{header: {frame_id: "map"}, '
            'pose: {pose: {position: {x: -2.0, y: -0.5, z: 0.0}, '
            'orientation: {x: 0.0, y: 0.0, z: 0.0, w: 1.0}}, '
            'covariance: [0.25, 0.0, 0.0, 0.0, 0.0, 0.0, '
            '0.0, 0.25, 0.0, 0.0, 0.0, 0.0, '
            '0.0, 0.0, 0.0, 0.0, 0.0, 0.0, '
            '0.0, 0.0, 0.0, 0.0, 0.0, 0.0, '
            '0.0, 0.0, 0.0, 0.0, 0.0, 0.0, '
            '0.0, 0.0, 0.0, 0.0, 0.0, 0.0685]}}'
        )
        ld.add_action(
            TimerAction(
                period=26.0,
                actions=[
                    ExecuteProcess(
                        cmd=[
                            'ros2', 'topic', 'pub', '--once',
                            '/initialpose',
                            'geometry_msgs/msg/PoseWithCovarianceStamped',
                            initial_pose_msg
                        ],
                        output='screen'
                    )
                ],
            )
        )
    #
    # RViz
    #
    ld.add_action(
        TimerAction(
            period=5.0,
            actions=[
                Node(
                    package='rviz2',
                    executable='rviz2',
                    output='screen',
                    parameters=[
                        {'use_sim_time': True}
                    ],
                    arguments=[
                        '-d',
                        rviz_config
                    ],
                )
            ],
        )
    )

    return ld