#!/bin/bash
###############################################################################
# Setup Script for Minimal GUI on Armbian-based Ubuntu Noble (ARMHF)
# No LightDM or display manager; autologin to TTY1 with Openbox + X11
###############################################################################

# CONFIG
USERNAME="orangepi"
AUTOLOGIN="yes"            # yes/no — auto-login to TTY1
SCREEN_ROTATION=90         # 0 = no rotation, 90 = vertical mode

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
echo "==> Creating ~/.xinitrc for Openbox..."
cat <<EOF > ~/.xinitrc
exec openbox-session
EOF

# Openbox autostart
echo "==> Creating Openbox autostart file..."
mkdir -p ~/.config/openbox
cat <<EOF > ~/.config/openbox/autostart
tint2 &
xterm &
conky &
EOF

# Optional: screen rotation
if [ "$SCREEN_ROTATION" = "90" ]; then
  echo "Adding screen rotation to autostart..."
  echo "(sleep 3 && xrandr --output \$(xrandr | grep ' connected' | cut -d' ' -f1) --rotate left) &" >> ~/.config/openbox/autostart
fi

# .bash_profile auto-start
echo "==> Enabling automatic startx on tty1..."
if ! grep -q "startx" ~/.bash_profile; then
  cat <<EOF >> ~/.bash_profile

# Start X only on tty1
if [[ -z "\$DISPLAY" ]] && [[ \$(tty) == /dev/tty1 ]]; then
  exec startx
fi
EOF
fi

# Set default browser
echo "==> Setting Epiphany as x-www-browser..."
sudo update-alternatives --install /usr/bin/x-www-browser x-www-browser /usr/bin/epiphany-browser 100
sudo update-alternatives --set x-www-browser /usr/bin/epiphany-browser

# Conky config with CPU temp
echo "==> Creating Conky config for temperature display..."
cat <<EOF > ~/.conkyrc
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

echo "==> Done. Reboot and enjoy your minimal GUI setup!"
