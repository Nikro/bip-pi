# Bip-Pi: ROS2 Robotics Platform

A ROS2-based robotics platform optimized for Raspberry Pi with a Pygame UI.

## Installation

Setup is simple with our all-in-one installation script:

```bash
git clone <this-repo-url>
cd bip-pi
chmod +x install.sh
./install.sh
```

This will:
1. Set up a lightweight GUI environment
2. Install ROS2 Humble
3. Configure your ROS2 workspace
4. Build the robotics platform

## Using the Platform

After installation, you can run the platform with:

```bash
# The environment is already set up by the installer
ros2 run robotics_platform main
```

To rebuild after making changes:

```bash
./colcon_build.sh
```

## Project Structure

- core: Core robotics loop
- ui: Pygame-based user interface
- ros2_nodes: ROS2 nodes for system functionality
- launch: ROS2 launch files
