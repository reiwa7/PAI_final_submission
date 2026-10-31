"""Gazebo + bridge only. Do NOT start manual teleop alongside AI."""
import os
from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import ExecuteProcess, SetEnvironmentVariable
from launch_ros.actions import Node


def generate_launch_description():
    share = Path(get_package_share_directory('nav_dev'))
    models = share / 'models'
    resource = str(models)
    old = os.environ.get('IGN_GAZEBO_RESOURCE_PATH', '')
    if old:
        resource += os.pathsep + old
    return LaunchDescription([
        SetEnvironmentVariable('IGN_GAZEBO_RESOURCE_PATH', resource),
        ExecuteProcess(cmd=['ign', 'gazebo', '-r', '-v', '3',
                            str(models / 'world.sdf')], output='screen'),
        Node(package='ros_gz_bridge', executable='parameter_bridge',
             parameters=[{'config_file': str(
                 share / 'config' / 'nav_teleop.yaml')}], output='screen'),
    ])
