from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        # Core robot nodes
        Node(
            package='robotics_platform',
            executable='robot_state_node',
            name='robot_state_node',
            output='screen'
        ),
        Node(
            package='robotics_platform',
            executable='ui_interface_node',
            name='ui_interface_node',
            output='screen'
        ),
        # Brain and awareness nodes
        Node(
            package='robotics_platform',
            executable='brain_node',
            name='brain_node',
            output='screen'
        ),
        Node(
            package='robotics_platform',
            executable='awareness_node',
            name='awareness_node',
            output='screen'
        )
    ])
