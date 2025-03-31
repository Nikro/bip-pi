from setuptools import setup

package_name = 'robotics_platform'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/robot.py']),
    ],
    install_requires=['setuptools'],  # Dependencies are managed by rosdep
    zip_safe=True,
    maintainer='Bip-Pi Team',
    maintainer_email='your.email@example.com',
    description='A robotics platform with a Pygame-based UI using ROS2',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'main = robotics_platform.main:main',
            'robot_state_node = robotics_platform.ros2_nodes.robot_state_node:main',
            'ui_interface_node = robotics_platform.ros2_nodes.ui_interface_node:main',
            'brain_node = robotics_platform.brain.language_model:main',
            'awareness_node = robotics_platform.awareness.monitor:main',
        ],
    },
)
