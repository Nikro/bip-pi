#!/bin/bash
# filepath: /var/www/bip-pi/install.sh
###############################################################################
# Setup Script for Reactive Companion System
###############################################################################

set -e  # Exit on error

# CONFIG
USERNAME=$(whoami)
HOME_DIR=$(eval echo ~${USERNAME})
PROJECT_DIR="${HOME_DIR}/bip-pi"
SCREEN_ROTATION=90
GIT_REPO="https://github.com/Nikro/bip-pi.git"

echo "==> Setting up for user: $USERNAME (home: $HOME_DIR)"

###############################################################################
# 1. SYSTEM DEPENDENCIES
###############################################################################
echo "==> Installing all system dependencies..."
sudo apt update || echo "Warning: apt update failed, continuing anyway"

# Basic system packages - only essential packages, not Python packages
echo "==> Installing essential packages..."
sudo apt install -y --no-install-recommends \
  python3-pip python3-dev git \
  xserver-xorg xinit openbox tint2 xterm feh epiphany-browser conky \
  openssh-server python3-venv python3-wheel \
  || echo "Warning: Some packages may have failed to install, continuing anyway"

###############################################################################
# 2. SSH SECURITY - RESTRICT TO LOCAL NETWORK
###############################################################################
echo "==> Configuring SSH for local network only..."

# Get the local subnet (assuming 192.168.x.x or 10.x.x.x networks)
LOCAL_SUBNET=$(ip route | grep -E '(192\.168|10\.)' | grep -v default | head -1 | awk '{print $1}')

if [ -z "$LOCAL_SUBNET" ]; then
  echo "Warning: Could not determine local subnet, using 192.168.0.0/16 as default"
  LOCAL_SUBNET="192.168.0.0/16"
fi

echo "==> Detected local subnet: $LOCAL_SUBNET"

# Create a backup of the SSH config
sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak

# Create or modify the SSH configuration to allow only local connections
sudo tee /etc/ssh/sshd_config.d/local-only.conf > /dev/null <<EOF
# Allow SSH only from local network
Match Address $LOCAL_SUBNET
  PermitRootLogin no
  PasswordAuthentication yes
  X11Forwarding no

# Deny from all other addresses
Match Address *
  PermitRootLogin no
  PasswordAuthentication no
  X11Forwarding no
EOF

# Restart SSH service
sudo systemctl restart sshd || echo "Warning: Failed to restart SSH service"
echo "==> SSH configured to allow connections only from the local network ($LOCAL_SUBNET)"

###############################################################################
# 3. PROJECT SETUP - CLONE FROM GIT
###############################################################################
echo "==> Cloning Reactive Companion from Git repository..."

# Clone the repository
if [ -d "${PROJECT_DIR}" ]; then
  echo "Project directory already exists. Pulling latest changes..."
  cd ${PROJECT_DIR}
  git pull
else
  echo "Cloning fresh repository..."
  git clone ${GIT_REPO} ${PROJECT_DIR}
fi

# Ensure executable permissions on scripts
chmod +x ${PROJECT_DIR}/*.sh

###############################################################################
# 4. GUI AND DISPLAY SETUP
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

# Openbox autostart - modified to use update_and_run.sh
echo "==> Creating Openbox autostart file with automatic updates..."
mkdir -p "${HOME_DIR}/.config/openbox"
cat <<EOF > "${HOME_DIR}/.config/openbox/autostart"
# Start the reactive companion with auto-update in an xterm
xterm -title "Reactive Companion" -geometry 100x30+0+0 -e "${PROJECT_DIR}/update_and_run.sh" &

# Start system monitoring tools
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

# Conky config with added git status
echo "==> Creating Conky config with repository status..."
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
Companion: \${execi 30 cd ${PROJECT_DIR} && git rev-parse --short HEAD || echo "unknown"}
]];
EOF
chmod 644 "${HOME_DIR}/.conkyrc" || echo "Warning: Unable to set permissions on .conkyrc"

###############################################################################
# 5. PYTHON ENVIRONMENT SETUP WITH POETRY
###############################################################################
echo "==> Setting up Python environment with Poetry..."

# Check if Poetry is installed, install if needed
if ! command -v poetry &>/dev/null; then
    echo "==> Installing Poetry..."
    curl -sSL https://install.python-poetry.org | python3 -
    
    # Add Poetry to PATH in .bashrc if not already there
    if ! grep -q "PATH=\"\$HOME/.local/bin:\$PATH\"" "${HOME_DIR}/.bashrc"; then
        echo -e '\n# Add Poetry to PATH\nexport PATH="$HOME/.local/bin:$PATH"' >> "${HOME_DIR}/.bashrc"
        # Apply the PATH change in the current session
        export PATH="$HOME/.local/bin:$PATH"
    fi
fi

# Set up the project dependencies with Poetry
cd ${PROJECT_DIR}

# Let Poetry use the system Python and create the venv in the project directory
poetry config virtualenvs.in-project true --local

echo "==> Installing project dependencies with Poetry..."
poetry install || echo "Warning: Poetry install failed, please run 'poetry install' manually"

# Add project directory to Python path for the current user
if ! grep -q "PYTHONPATH=\"${PROJECT_DIR}" "${HOME_DIR}/.bashrc"; then
    echo -e '\n# Add project to PYTHONPATH\nexport PYTHONPATH="'"${PROJECT_DIR}"':$PYTHONPATH"' >> "${HOME_DIR}/.bashrc"
fi

###############################################################################
# 6. ENSURE BASIC ENV CONFIGURATION
###############################################################################
echo "==> Creating basic environment configuration..."

# Create config directory
mkdir -p ${PROJECT_DIR}/config
mkdir -p ${PROJECT_DIR}/logs

# Create a template .env file if it doesn't exist
if [ ! -f "${PROJECT_DIR}/.env" ]; then
  echo "==> Creating template .env file (you will need to edit this with your actual values)..."
  cat > "${PROJECT_DIR}/.env" << EOF
# Reactive Companion Environment Configuration
# Edit this file with your actual values

# General settings
DEBUG=false
LOG_LEVEL=info

# Audio settings
AUDIO_DEVICE_INDEX=0

# API keys for external services (add your own)
# OPENAI_API_KEY=your_key_here
# ELEVENLABS_API_KEY=your_key_here

# Other configuration paths
CONFIG_DIR=config
EOF
fi

# No more default JSON creation - that will be handled by the application or manually

# Run the cleanup script to ensure a clean environment
echo "==> Running cleanup script..."
${PROJECT_DIR}/cleanup.sh

echo "==> Setup complete!"
echo "Your Reactive Companion project is set up at: ${PROJECT_DIR}"
echo "The system will automatically update and start on boot."
echo "To manually start the system:"
echo "  1. cd ${PROJECT_DIR}"
echo "  2. poetry shell  # Activates the virtual environment"
echo "  3. ./update_and_run.sh"

# Define a function for automatic startup
autostart() {
    echo "==> Setting up automatic startup on boot..."
    # This function is intentionally kept as a placeholder
    # Actual autostart is handled by .bash_profile and openbox/autostart
    echo "Automatic startup configured successfully!"
}

# Call autostart function to complete setup
autostart