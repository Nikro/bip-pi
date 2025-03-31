#!/bin/bash
###############################################################################
# Setup Script for Minimal GUI on Armbian-based Ubuntu Noble (ARMHF)
# No LightDM or display manager; autologin to TTY1 with Openbox + X11
###############################################################################

# CONFIG
USERNAME=$(whoami)  # Get current username
AUTOLOGIN="yes"     # yes/no — auto-login to TTY1
SCREEN_ROTATION=90  # 0 = no rotation, 90 = vertical mode
HOME_DIR=$(eval echo ~${USERNAME})  # Get correct home directory

echo "==> Setting up for user: $USERNAME (home: $HOME_DIR)"

echo "==> Updating system..."
sudo apt update && sudo apt upgrade -y

echo "==> Installing lightweight GUI stack..."
sudo apt install -y --no-install-recommends \
  xserver-xorg xinit openbox tint2 xterm feh \
  epiphany-browser git python3 python3-pip conky

# Auto-login setup
if [ "$AUTOLOGIN" = "yes" ]; then
  echo "==> Enabling auto-login for $USERNAME on tty1..."
  sudo mkdir -p /etc/systemd/system/getty@tty1.service.d
  sudo tee /etc/systemd/system/getty@tty1.service.d/override.conf > /dev/null <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $USERNAME --noclear %I 38400 linux
EOF
  sudo systemctl daemon-reexec
  sudo systemctl daemon-reload
  sudo systemctl restart getty@tty1.service
fi

# .xinitrc
echo "==> Creating .xinitrc for Openbox..."
cat <<EOF > "${HOME_DIR}/.xinitrc"
exec openbox-session
EOF
chown ${USERNAME}:${USERNAME} "${HOME_DIR}/.xinitrc"

# Openbox autostart
echo "==> Creating Openbox autostart file..."
mkdir -p "${HOME_DIR}/.config/openbox"
cat <<EOF > "${HOME_DIR}/.config/openbox/autostart"
tint2 &
xterm &
conky &
EOF
chown -R ${USERNAME}:${USERNAME} "${HOME_DIR}/.config"

# Configure screen rotation via X11 instead of runtime xrandr
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
if ! grep -q "startx" "${HOME_DIR}/.bash_profile"; then
  cat <<EOF >> "${HOME_DIR}/.bash_profile"

# Start X only on tty1
if [[ -z "\$DISPLAY" ]] && [[ \$(tty) == /dev/tty1 ]]; then
  exec startx
fi
EOF
fi
chown ${USERNAME}:${USERNAME} "${HOME_DIR}/.bash_profile"

# Set default browser
echo "==> Setting Epiphany as x-www-browser..."
sudo update-alternatives --install /usr/bin/x-www-browser x-www-browser /usr/bin/epiphany-browser 100
sudo update-alternatives --set x-www-browser /usr/bin/epiphany-browser

# Conky config with CPU temp
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
chown ${USERNAME}:${USERNAME} "${HOME_DIR}/.conkyrc"

echo "==> Done. Reboot and enjoy your minimal GUI setup!"
