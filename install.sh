#!/bin/bash
###############################################################################
# Setup Script for ROS2 on Debian Bookworm (ARM) with Minimal GUI
###############################################################################

set -e  # Exit on error

# CONFIG
USERNAME=$(whoami)
HOME_DIR=$(eval echo ~${USERNAME})
WORKSPACE_DIR="${HOME_DIR}/ros2_ws"
VENV_DIR="${HOME_DIR}/.venv/bip-pi"
SCREEN_ROTATION=90

echo "==> Setting up for user: $USERNAME (home: $HOME_DIR)"

# Ensure we have required packages for the installation
echo "==> Installing required system packages..."
sudo apt update
sudo apt install -y --no-install-recommends \
  curl gnupg lsb-release python3-pip python3-venv python3-full \
  git make cmake g++ xserver-xorg xinit openbox tint2 xterm feh \
  epiphany-browser conky 

# Set up a Python virtual environment
echo "==> Creating Python virtual environment..."
python3 -m venv ${VENV_DIR}
echo "Created Python venv at: ${VENV_DIR}"
source ${VENV_DIR}/bin/activate

# Install Python packages in the virtual env
echo "==> Installing Python packages in virtual environment..."
pip install --upgrade pip
pip install pygame emoji setuptools build colcon-common-extensions

# Set up ROS2 - using binary distribution if possible
echo "==> Setting up ROS2..."

# Create workspace
echo "==> Creating ROS2 workspace..."
mkdir -p ${WORKSPACE_DIR}/src

# Link our repository to the workspace
echo "==> Linking repository to workspace..."
ln -sf "$(pwd)" "${WORKSPACE_DIR}/src/robotics_platform"

# Add environment setup to .bashrc
echo "==> Adding environment setup to .bashrc..."
if ! grep -q "source ${VENV_DIR}/bin/activate" "${HOME_DIR}/.bashrc"; then
  cat <<EOF >> "${HOME_DIR}/.bashrc"

# Robotics platform environment
if [ -f "${VENV_DIR}/bin/activate" ]; then
    source "${VENV_DIR}/bin/activate"
fi

# ROS2 workspace
if [ -f "${WORKSPACE_DIR}/install/setup.bash" ]; then
    source "${WORKSPACE_DIR}/install/setup.bash"
fi
EOF
fi

# Now build our robotics platform - locally
echo "==> Building robotics platform..."
cd ${WORKSPACE_DIR}
colcon build --symlink-install --packages-select robotics_platform

# Configure GUI/screen rotation
echo "==> Setting up GUI configuration..."

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
if [ -f "${VENV_DIR}/bin/activate" ]; then
    source "${VENV_DIR}/bin/activate"
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

# Update colcon_build.sh to use our virtual environment
echo "==> Updating colcon_build.sh..."
cat > "$(pwd)/colcon_build.sh" << 'EOF'
#!/bin/bash

set -e  # Exit on error

echo "==> Setting up and building with colcon..."

# Activate virtual environment if available
VENV_DIR="${HOME}/.venv/bip-pi"
if [ -f "${VENV_DIR}/bin/activate" ]; then
    echo "==> Activating virtual environment..."
    source "${VENV_DIR}/bin/activate"
fi

# Create workspace if it doesn't exist
WORKSPACE_DIR="${HOME}/ros2_ws"
mkdir -p ${WORKSPACE_DIR}/src

# Link current repository to workspace
echo "==> Linking repository to ROS2 workspace..."
ln -sf "$(pwd)" "${WORKSPACE_DIR}/src/robotics_platform"

# Change to workspace directory
cd ${WORKSPACE_DIR}

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
EOF
chmod +x "$(pwd)/colcon_build.sh"

echo "==> Setup complete! To use robotics platform:"
echo ""
echo "  1. Activate environment: source ${VENV_DIR}/bin/activate"
echo "  2. Start the platform: ros2 launch robotics_platform robot.py"
echo ""
echo "==> Or reboot to start automatically with the GUI"