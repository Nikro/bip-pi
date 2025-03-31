#!/bin/bash
###############################################################################
# install_ai_desktop.sh
#
# This script sets up only the essential components needed for AI development
# on an Orange Pi with LightDM already installed:
#
#   STEP 0: Adjusts APT sources to use the official Debian Buster repositories
#           for armhf devices.
#   STEP 1: Updates and upgrades system packages.
#   STEP 2: Installs only the required packages (Git, Python3).
#   STEP 3: Configures screen rotation for vertical display.
#
# Configuration Variables:
SCREEN_ROTATION=90      # 0 = no rotation; 90 = rotate 90° (for vertical display)
DEBIAN_VERSION="buster" # Debian release name
###############################################################################

# ---------------------------
# STEP 0: Update APT Mirrors for armhf Devices
# ---------------------------
echo "==> Updating APT sources to use the official Debian Buster repositories for armhf..."
# Back up the current sources.list file
sudo cp /etc/apt/sources.list /etc/apt/sources.list.backup

# Overwrite with Debian Buster repositories for armhf devices
sudo bash -c "cat > /etc/apt/sources.list <<EOF
deb [arch=armhf] http://deb.debian.org/debian ${DEBIAN_VERSION} main contrib non-free
deb [arch=armhf] http://deb.debian.org/debian ${DEBIAN_VERSION}-updates main contrib non-free
deb [arch=armhf] http://security.debian.org/debian-security ${DEBIAN_VERSION}/updates main contrib non-free
EOF"

# ---------------------------
# STEP 1: Update and Upgrade System Packages
# ---------------------------
echo "==> Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# ---------------------------
# STEP 2: Install Required Packages
# ---------------------------
echo "==> Installing only essential packages..."
sudo apt-get install -y --no-install-recommends \
    git python3 python3-pip xrandr

# ---------------------------
# STEP 3: Configure Screen Rotation
# ---------------------------
if [ "$SCREEN_ROTATION" -eq 90 ]; then
    echo "==> Configuring screen rotation (90 degrees)..."
    
    # Create xorg configuration for rotation
    sudo mkdir -p /etc/X11/xorg.conf.d/
    sudo tee /etc/X11/xorg.conf.d/90-monitor.conf > /dev/null <<EOF
Section "Monitor"
    Identifier "HDMI-1"
    Option "Rotate" "left"
EndSection
EOF

    # Make sure the system applies rotation on next boot
    echo "Screen rotation configured. It will take effect after reboot."
fi

# ---------------------------
# DONE
# ---------------------------
echo "==> Setup complete. Please reboot your system to apply all changes."
