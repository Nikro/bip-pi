#!/bin/bash

set -e  # Exit on error

echo "==> Setting up and building with colcon..."

# Create workspace if it doesn't exist
WORKSPACE_DIR="${HOME}/ros2_ws"
mkdir -p ${WORKSPACE_DIR}/src

# Link current repository to workspace
echo "==> Linking repository to ROS2 workspace..."
ln -sf "$(pwd)" "${WORKSPACE_DIR}/src/robotics_platform"

# Source ROS2 environment if available
if [ -f "/opt/ros/humble/setup.bash" ]; then
    source /opt/ros/humble/setup.bash
fi

# Change to workspace directory
cd ${WORKSPACE_DIR}

# Install dependencies if rosdep is available
if command -v rosdep &> /dev/null; then
    echo "==> Installing dependencies with rosdep..."
    rosdep update
    rosdep install --from-paths src --ignore-src -y
else
    echo "==> rosdep not found, skipping dependency installation."
fi

# Build with colcon
if command -v colcon &> /dev/null; then
    echo "==> Building with colcon..."
    colcon build --symlink-install
else
    echo "==> colcon not found, cannot build package"
    echo "==> Try running the install.sh script to install colcon"
    exit 1
fi

# Run tests if requested
if [ "$1" == "--test" ]; then
    echo "==> Running tests..."
    colcon test
    colcon test-result --verbose
fi

echo "==> Build complete! To use the built packages:"
echo ""
echo "  source ${WORKSPACE_DIR}/install/setup.bash"
echo "  ros2 launch robotics_platform robot.py"
echo ""
