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
# 1. SYSTEM DEPENDENCIES - Everything needed by the OS/display
###############################################################################
echo "==> Installing system dependencies..."
sudo apt update
sudo apt install -y --no-install-recommends \
  # Base build tools
  build-essential curl gnupg lsb-release \
  # GUI environment
  xserver-xorg xinit openbox tint2 xterm feh epiphany-browser conky \
  # Python core
  python3-dev python3-pip \
  # Pygame system dependencies
  python3-pygame libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev \
  libsdl2-ttf-dev libfreetype-dev libportmidi-dev \
  # Tools
  git

###############################################################################
# 2. ROS2 SETUP - Use ROS's own tools for dependency management
###############################################################################
echo "==> Setting up ROS2..."

# Try to add ROS2 repositories (works on Ubuntu)
if grep -q "Ubuntu\|Debian" /etc/os-release; then
  DISTRO=$(grep -oP '(?<=VERSION_CODENAME=).+' /etc/os-release)
  echo "==> Detected distribution: $DISTRO, adding ROS2 repositories..."
  
  sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    -o /usr/share/keyrings/ros-archive-keyring.gpg
    
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
    http://packages.ros.org/ros2/ubuntu $DISTRO main" | \
    sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
    
  sudo apt update
  
  # Install ROS2 and essential tools
  sudo apt install -y ros-humble-ros-base python3-rosdep python3-colcon-common-extensions
  
  # Initialize rosdep if needed
  if [ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]; then
    sudo rosdep init
  fi
  rosdep update
else
  # Fallback for systems without ROS2 packages
  echo "==> ROS2 packages not available. Installing minimal ROS2 Python libraries..."
  pip3 install --user rclpy
fi

###############################################################################
# 3. PROJECT SETUP - Set up our robotics platform
###############################################################################
echo "==> Setting up robotics platform workspace..."

# Create workspace
mkdir -p ${WORKSPACE_DIR}/src
ln -sf "$(pwd)" "${WORKSPACE_DIR}/src/robotics_platform"

# Install dependencies using rosdep if available
cd ${WORKSPACE_DIR}
if command -v rosdep &> /dev/null; then
  echo "==> Installing project dependencies with rosdep..."
  rosdep install --from-paths src --ignore-src -y
else
  echo "==> Installing project dependencies with pip..."
  pip3 install --user pygame emoji
fi

# Build the workspace
if command -v colcon &> /dev/null; then
  echo "==> Building with colcon..."
  colcon build --symlink-install
else
  echo "==> Colcon not available, skipping build..."
fi

###############################################################################
# 4. ENVIRONMENT SETUP - Configure remaining GUI and startup
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
  sudo systemctl daemon-reexec || true
  sudo systemctl daemon-reload || true
  sudo systemctl restart getty@tty1.service || true
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
if [ -f "${WORKSPACE_DIR}/install/setup.bash" ]; then
    source "${WORKSPACE_DIR}/install/setup.bash"
    xterm -e "ros2 launch robotics_platform robot.py" &
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
chmod 755 "${HOME_DIR}/.bash_profile"

# Set default browser
echo "==> Setting Epiphany as x-www-browser..."
sudo update-alternatives --install /usr/bin/x-www-browser x-www-browser /usr/bin/epiphany-browser 100
sudo update-alternatives --set x-www-browser /usr/bin/epiphany-browser

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
chmod 644 "${HOME_DIR}/.conkyrc"

echo "==> Setup complete!"
echo "To use the robotics platform:"
echo "  1. Run: source ${WORKSPACE_DIR}/install/setup.bash"
echo "  2. Start platform: ros2 launch robotics_platform robot.py"