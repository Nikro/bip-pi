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
# 1. SYSTEM DEPENDENCIES - Using a single apt command
###############################################################################
echo "==> Installing all system dependencies..."
sudo apt update || echo "Warning: apt update failed, continuing anyway"

# Single apt command for all packages
echo "==> Installing all required packages..."
sudo apt install -y --no-install-recommends \
  python3-pip python3-dev git \
  xserver-xorg xinit openbox tint2 xterm feh epiphany-browser conky \
  python3-setuptools python3-pygame python3-emoji python3-rclpy \
  || echo "Warning: Some packages may have failed to install, continuing anyway"

###############################################################################
# 2. PROJECT SETUP
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
# 3. GUI AND DISPLAY SETUP
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
# 4. PACKAGE SETUP
###############################################################################
echo "==> Configuring package files..."

# Simplify pyproject.toml
cat > pyproject.toml << EOF
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"
EOF

# Try to do a pip install of the current package only if needed
echo "==> Installing the robotics platform package..."
if ! python3 -c "import robotics_platform" &>/dev/null; then
  pip3 install --user -e . || echo "Warning: Failed to install package, continuing anyway"
fi

echo "==> Setup complete! To start the robotics platform:"
echo "  1. Run: source ${WORKSPACE_DIR}/setup.bash"
echo "  2. Start the platform: ros2_run"