#!/bin/bash
###############################################################################
# Setup Script for Bip-Pi ROS2 Robotics Platform
###############################################################################

set -e  # Exit on error

# CONFIG
USERNAME=$(whoami)
HOME_DIR=$(eval echo ~${USERNAME})
WORKSPACE_DIR="${HOME_DIR}/ros2_ws"
SCREEN_ROTATION=90

echo "==> Setting up for user: $USERNAME (home: $HOME_DIR)"

###############################################################################
# 1. SYSTEM DEPENDENCIES - Installing one by one with error handling
###############################################################################
echo "==> Installing system dependencies..."
sudo apt update || echo "Warning: apt update failed, continuing anyway"

# Function to install packages with error handling
install_pkg() {
  sudo apt install -y --no-install-recommends $1 || echo "Warning: Failed to install $1, continuing anyway"
}

# Install core packages one by one
echo "==> Installing Python and development tools..."
install_pkg "python3-pip"
install_pkg "python3-dev"
install_pkg "git"

echo "==> Installing GUI components..."
install_pkg "xserver-xorg" 
install_pkg "xinit"
install_pkg "openbox"
install_pkg "tint2"
install_pkg "xterm"
install_pkg "feh"
install_pkg "epiphany-browser"
install_pkg "conky"

echo "==> Installing Pygame dependencies..."
install_pkg "python3-pygame"
install_pkg "libsdl2-dev"
install_pkg "libsdl2-ttf-dev"

###############################################################################
# 2. PYTHON DEPENDENCIES - Using pip with --user flag
###############################################################################
echo "==> Installing Python packages..."
pip3 install --user rclpy || echo "Warning: Failed to install rclpy, continuing"
pip3 install --user emoji || echo "Warning: Failed to install emoji, continuing"

# Only try pygame via pip if system install failed
if ! python3 -c "import pygame" &>/dev/null; then
  echo "==> Installing pygame via pip..."
  pip3 install --user pygame || echo "Warning: Failed to install pygame, continuing"
fi

###############################################################################
# 3. PROJECT SETUP
###############################################################################
echo "==> Setting up robotics platform workspace..."

# Create workspace
mkdir -p ${WORKSPACE_DIR}/src
ln -sf "$(pwd)" "${WORKSPACE_DIR}/src/robotics_platform"

# Create simple setup script that will work without colcon
cat > ${WORKSPACE_DIR}/setup.bash << EOF
#!/bin/bash
# Simple setup script for robotics platform

# Add the source directory to PYTHONPATH
export PYTHONPATH=\${PYTHONPATH}:${WORKSPACE_DIR}/src

# Minimal ROS2 functions
ros2_run() {
  python3 -m robotics_platform.main
}

ros2_launch() {
  python3 -m robotics_platform.main
}

# If colcon build exists and succeeded, source it
if [ -f "${WORKSPACE_DIR}/install/setup.bash" ]; then
    source "${WORKSPACE_DIR}/install/setup.bash"
else
    # Otherwise, create minimal ros2 command
    alias ros2="echo 'Using minimal ROS2 implementation'; echo '- ros2 run robotics_platform main: use ros2_run'"
fi

echo "Robotics platform environment activated"
EOF

chmod +x ${WORKSPACE_DIR}/setup.bash

# Add environment setup to .bashrc
echo "==> Adding environment setup to .bashrc..."
if ! grep -q "${WORKSPACE_DIR}/setup.bash" "${HOME_DIR}/.bashrc"; then
  cat <<EOF >> "${HOME_DIR}/.bashrc"

# Robotics platform setup
if [ -f "${WORKSPACE_DIR}/setup.bash" ]; then
    source "${WORKSPACE_DIR}/setup.bash"
fi
EOF
fi

###############################################################################
# 4. GUI AND DISPLAY SETUP - Keep this section intact
###############################################################################

# Auto-login setup
echo "==> Enabling auto-login for $USERNAME on tty1..."
if [ -d "/etc/systemd/system" ]; then
  sudo mkdir -p /etc/systemd/system/getty@tty1.service.d
  sudo tee /etc/systemd/system/getty@tty1.service.d/override.conf > /dev/null <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $USERNAME --noclear %I 38400 linux
EOF
  sudo systemctl daemon-reexec 2>/dev/null || true
  sudo systemctl daemon-reload 2>/dev/null || true
  sudo systemctl restart getty@tty1.service 2>/dev/null || true
fi

# .xinitrc
echo "==> Creating .xinitrc for Openbox..."
cat <<EOF > "${HOME_DIR}/.xinitrc"
exec openbox-session
EOF
chmod 755 "${HOME_DIR}/.xinitrc"

# Openbox autostart
echo "==> Creating Openbox autostart file..."
mkdir -p "${HOME_DIR}/.config/openbox"
cat <<EOF > "${HOME_DIR}/.config/openbox/autostart"
# Activate our environment and start the robot UI
if [ -f "${WORKSPACE_DIR}/setup.bash" ]; then
    source "${WORKSPACE_DIR}/setup.bash"
    xterm -e "ros2_run" &
fi

tint2 &
conky &
EOF
chmod 755 "${HOME_DIR}/.config/openbox/autostart"

# Configure screen rotation if needed
if [ "$SCREEN_ROTATION" -eq 90 ]; then 
  echo "==> Configuring screen rotation via X11 (90 degrees)..."
  sudo mkdir -p /etc/X11/xorg.conf.d/
  sudo tee /etc/X11/xorg.conf.d/90-monitor.conf > /dev/null <<EOF
Section "Monitor"
    Identifier "HDMI-1"
    Option "Rotate" "left"
EndSection

Section "Screen"
    Identifier "Screen0"
    Monitor "HDMI-1"
EndSection
EOF
fi

# .bash_profile auto-start
echo "==> Enabling automatic startx on tty1..."
cat <<EOF > "${HOME_DIR}/.bash_profile"
# Source .bashrc
if [ -f "\${HOME}/.bashrc" ]; then
    source "\${HOME}/.bashrc"
fi

# Start X only on tty1
if [[ -z "\$DISPLAY" ]] && [[ \$(tty) == /dev/tty1 ]]; then
  exec startx
fi
EOF
chmod 755 "${HOME_DIR}/.bash_profile" || echo "Warning: Unable to set permissions on .bash_profile"

# Set default browser
echo "==> Setting Epiphany as x-www-browser..."
if command -v epiphany-browser &>/dev/null; then
  sudo update-alternatives --install /usr/bin/x-www-browser x-www-browser /usr/bin/epiphany-browser 100 || true
  sudo update-alternatives --set x-www-browser /usr/bin/epiphany-browser || true
fi

# Conky config
echo "==> Creating Conky config for temperature display..."
cat <<EOF > "${HOME_DIR}/.conkyrc"
conky.config = {
    alignment = 'top_right',
    background = true,
    update_interval = 3.0,
    double_buffer = true,
    own_window = true,
    own_window_type = 'desktop',
    own_window_transparent = true,
    font = 'DejaVu Sans Mono:size=10',
};

conky.text = [[
Time: \${time %H:%M:%S}
CPU Temp: \${execi 3 awk '{ printf("%.1f°C", \$1 / 1000) }' /sys/class/thermal/thermal_zone0/temp}
CPU Usage: \${cpu}%
RAM: \$mem / \$memmax
]];
EOF
chmod 644 "${HOME_DIR}/.conkyrc" || echo "Warning: Unable to set permissions on .conkyrc"

###############################################################################
# 5. CLEANUP UNNECESSARY PROJECT FILES
###############################################################################
echo "==> Cleaning up redundant files..."

# Update setup.py with direct dependencies instead of relying on rosdep
sed -i 's/install_requires=\[.*\]/install_requires=["setuptools", "rclpy", "pygame", "emoji"]/' setup.py || echo "Warning: Failed to update setup.py"

# Simplify pyproject.toml
cat > pyproject.toml << EOF
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
testpaths = ["test"]
python_files = "test_*.py"
EOF

# Try to do a pip install of the current package
echo "==> Installing the robotics platform package..."
pip3 install --user -e . || echo "Warning: Failed to install package, continuing anyway"

echo "==> Setup complete! To start the robotics platform:"
echo "  1. Run: source ${WORKSPACE_DIR}/setup.bash"
echo "  2. Start the platform: ros2_run"