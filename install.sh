#!/bin/bash
# filepath: /var/www/bip-pi/install.sh
###############################################################################
# Setup Script for Reactive Companion System
###############################################################################

set -e  # Exit on error

# Display a visual separator for better readability in the terminal
separator() {
  echo "====================================================================="
  echo "$1"
  echo "====================================================================="
}

# CONFIG
USERNAME=$(whoami)
HOME_DIR=$(eval echo ~${USERNAME})
PROJECT_DIR="${HOME_DIR}/bip-pi"
SCREEN_ROTATION=90
GIT_REPO="https://github.com/Nikro/bip-pi.git"

separator "Setting up for user: $USERNAME (home: $HOME_DIR)"

###############################################################################
# 1. SYSTEM DEPENDENCIES
###############################################################################
separator "Installing all system dependencies..."
sudo apt update || echo "Warning: apt update failed, continuing anyway"

# Basic system packages - only essential packages, not Python packages
separator "Installing essential packages..."
sudo apt install -y --no-install-recommends \
  python3-pip python3-dev git \
  xserver-xorg xinit openbox tint2 xterm feh epiphany-browser conky \
  openssh-server python3-venv python3-wheel \
  zenity xterm \
  || echo "Warning: Some packages may have failed to install, continuing anyway"

# Install audio, PyGame, and graphics dependencies
separator "Installing audio and graphics dependencies..."
sudo apt install -y \
  portaudio19-dev libasound2-dev libportaudio2 \
  libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
  libfreetype6-dev libportmidi-dev \
  pkg-config \
  || echo "Warning: Some audio/graphics packages may have failed to install, continuing anyway"

###############################################################################
# 2. SSH SECURITY - RESTRICT TO LOCAL NETWORK
###############################################################################
separator "Configuring SSH for local network only..."

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
separator "Cloning Reactive Companion from Git repository..."

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
separator "Enabling auto-login for $USERNAME on tty1..."
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
separator "Creating .xinitrc for Openbox..."
cat <<EOF > "${HOME_DIR}/.xinitrc"
exec openbox-session
EOF
chmod 755 "${HOME_DIR}/.xinitrc"

# Openbox autostart - modified to use update_and_run.sh
separator "Creating Openbox autostart file with automatic updates..."
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
  separator "Configuring screen rotation via X11 (90 degrees)..."
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
separator "Enabling automatic startx on tty1..."
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
separator "Setting Epiphany as x-www-browser..."
if command -v epiphany-browser &>/dev/null; then
  sudo update-alternatives --install /usr/bin/x-www-browser x-www-browser /usr/bin/epiphany-browser 100 || true
  sudo update-alternatives --set x-www-browser /usr/bin/epiphany-browser || true
fi

# Conky config with added git status
separator "Creating Conky config with repository status..."
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
# 5. PYTHON ENVIRONMENT SETUP WITH PIP AND VENV
###############################################################################
separator "Setting up Python environment"

# Install build dependencies needed for Python packages
separator "Installing build dependencies"
sudo apt install -y \
  libffi-dev build-essential python3-dev \
  libjpeg-dev libpng-dev \
  || echo "Warning: Some build dependencies may have failed to install, continuing anyway"

# Check Python version
PYTHON_VERSION=$(python3 --version 2>/dev/null | cut -d ' ' -f 2) || PYTHON_VERSION="0.0.0"
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d '.' -f 1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d '.' -f 2)

echo "==> Detected Python version: $PYTHON_VERSION"

# Check if Python version is adequate (we need at least 3.10)
if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    echo "==> Python version $PYTHON_VERSION is below the required 3.10"
    echo "==> Attempting to install Python 3.10 or later..."
    
    # Try to install Python 3.10
    if command -v add-apt-repository &>/dev/null; then
        # Add deadsnakes PPA if it doesn't exist
        if ! grep -q "deadsnakes/ppa" /etc/apt/sources.list /etc/apt/sources.list.d/* 2>/dev/null; then
            echo "==> Adding deadsnakes PPA..."
            sudo add-apt-repository -y ppa:deadsnakes/ppa
            sudo apt update
        fi
        
        # Try Python 3.11 first (if available)
        echo "==> Attempting to install Python 3.11..."
        if sudo apt install -y python3.11 python3.11-venv python3.11-dev; then
            if command -v python3.11 &>/dev/null; then
                echo "==> Successfully installed Python 3.11"
                PYTHON_CMD="python3.11"
            fi
        else
            echo "==> Python 3.11 not available, trying Python 3.10..."
        fi
        
        # If Python 3.11 failed or not available, try Python 3.10
        if [ -z "$PYTHON_CMD" ] || [ "$PYTHON_CMD" = "python3" ]; then
            echo "==> Installing Python 3.10..."
            sudo apt install -y python3.10 python3.10-venv python3.10-dev
            
            if command -v python3.10 &>/dev/null; then
                echo "==> Successfully installed Python 3.10"
                PYTHON_CMD="python3.10"
            else
                echo "==> ERROR: Could not install Python 3.10."
                echo "==> Poetry 2.1.2 requires Python 3.10 or later. Installation cannot continue."
                exit 1
            fi
        fi
    else
        echo "==> ERROR: Could not add PPA to install Python 3.10+."
        echo "==> Poetry 2.1.2 requires Python 3.10 or later. Installation cannot continue."
        exit 1
    fi
else
    echo "==> Python version $PYTHON_VERSION meets requirements"
    PYTHON_CMD="python3"
fi

# Create virtual environment with the appropriate Python version
cd ${PROJECT_DIR}
echo "==> Creating virtual environment using $($PYTHON_CMD --version)..."
$PYTHON_CMD -m venv .venv

# Activate the virtual environment
source .venv/bin/activate

# Upgrade pip
echo "==> Upgrading pip..."
pip install --upgrade pip setuptools wheel

# Install Poetry 2.1.2 or later
echo "==> Installing Poetry 2.1.2 or later..."
pip install "poetry>=2.1.2"

# Pre-install problematic packages with pip before using Poetry
echo "==> Pre-installing packages that might cause build issues..."
pip install wheel
pip install --no-build-isolation pyaudio pygame

# Verify Poetry installation
if command -v poetry &>/dev/null; then
    POETRY_VERSION=$(poetry --version | awk '{print $3}')
    echo "==> Poetry $POETRY_VERSION installed successfully!"
    
    # Verify Poetry version meets minimum requirements
    POETRY_MAJOR=$(echo $POETRY_VERSION | cut -d'.' -f1)
    POETRY_MINOR=$(echo $POETRY_VERSION | cut -d'.' -f2)
    POETRY_PATCH=$(echo $POETRY_VERSION | cut -d'.' -f3 | cut -d'-' -f1) # Handle potential beta versions
    
    if [ "$POETRY_MAJOR" -lt 2 ] || ([ "$POETRY_MAJOR" -eq 2 ] && [ "$POETRY_MINOR" -lt 1 ]) || ([ "$POETRY_MAJOR" -eq 2 ] && [ "$POETRY_MINOR" -eq 1 ] && [ "$POETRY_PATCH" -lt 2 ]); then
        echo "==> WARNING: Poetry version $POETRY_VERSION is below the required 2.1.2."
        echo "==> This might cause compatibility issues with the project."
    fi
    
    # Configure Poetry to use the virtual environment we just created
    poetry config virtualenvs.in-project true --local
    
    echo "==> Installing project dependencies with Poetry..."
    if poetry install; then
        echo "==> Dependencies installed successfully!"
    else
        echo "==> WARNING: Poetry install failed. Checking Python compatibility..."
        
        # Get the required Python version from pyproject.toml
        REQUIRED_PYTHON=$(grep "python =" ${PROJECT_DIR}/pyproject.toml | head -1 | cut -d '"' -f 2 | sed 's/\^//')
        echo "==> Project requires Python $REQUIRED_PYTHON"
        
        if [ "$PYTHON_MAJOR" -lt "${REQUIRED_PYTHON%%.*}" ] || ([ "$PYTHON_MAJOR" -eq "${REQUIRED_PYTHON%%.*}" ] && [ "$PYTHON_MINOR" -lt "$(echo $REQUIRED_PYTHON | cut -d '.' -f 2)" ]); then
            echo "==> ERROR: Your Python version ($PYTHON_VERSION) is lower than the required version ($REQUIRED_PYTHON)"
            echo "==> Please install Python $REQUIRED_PYTHON or later and run this script again"
        fi
        
        echo "==> Installing core dependencies directly with pip as fallback..."
        pip install -U pyzmq numpy psutil pydantic python-dotenv pygame
        # Note: PyAudio and Pygame should already be installed from the pre-install step
    fi
else
    echo "==> ERROR: Poetry installation failed!"
    echo "==> This is critical as Poetry 2.1.2+ is required for managing project dependencies."
    echo "==> The fallback installation with pip might not include all required dependencies."
    echo "==> Installing core dependencies directly with pip as emergency fallback..."
    pip install -U pyzmq pygame pyaudio numpy psutil pydantic python-dotenv
fi

###############################################################################
# 6. ENSURE BASIC ENV CONFIGURATION
###############################################################################
separator "Creating basic environment configuration"

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
separator "Running cleanup script..."
${PROJECT_DIR}/cleanup.sh

separator "Setup complete!"
echo "Your Reactive Companion project is set up at: ${PROJECT_DIR}"
echo "The system will automatically update and start on boot."
echo "To manually start the system:"
echo "  1. cd ${PROJECT_DIR}"
echo "  2. poetry shell  # Activates the virtual environment"
echo "  3. ./update_and_run.sh"

# Define a function for automatic startup
autostart() {
    separator "Setting up automatic startup on boot..."
    # This function is intentionally kept as a placeholder
    # Actual autostart is handled by .bash_profile and openbox/autostart
    echo "Automatic startup configured successfully!"
}

# Call autostart function to complete setup
autostart