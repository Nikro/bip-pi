#!/bin/bash

set -e  # Exit on error

echo "==> Setting up and building with colcon..."

# Create workspace if it doesn't exist
WORKSPACE_DIR="../ros2_ws"
mkdir -p ${WORKSPACE_DIR}/src

# Link current repository to workspace
echo "==> Linking repository to ROS2 workspace..."
ln -sf "$(pwd)" "${WORKSPACE_DIR}/src/robotics_platform"

# Change to workspace directory
cd ${WORKSPACE_DIR}

# Install dependencies if rosdep is available
if command -v rosdep &> /dev/null; then
    echo "==> Installing dependencies with rosdep..."
    rosdep update
    rosdep install --from-paths src --ignore-src -y
else
    echo "==> rosdep not found, skipping dependency installation."
    echo "==> Install manually with: pip install pygame emoji"
fi

# Build with colcon
echo "==> Building with colcon..."
colcon build --symlink-install

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
