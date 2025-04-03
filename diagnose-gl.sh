#!/bin/bash
# OpenGL Diagnostics for ARM/Lima/Mali devices

# Create log file
LOG_FILE="/tmp/opengl-diagnostics.log"
echo "OpenGL Diagnostics Report: $(date)" > "$LOG_FILE"

# Helper function
log() {
    echo "==== $1 ====" | tee -a "$LOG_FILE"
    if [ -n "$2" ]; then
        eval "$2" 2>&1 | tee -a "$LOG_FILE"
    fi
    echo "" | tee -a "$LOG_FILE"
}

# Make sure we can properly access X display
export DISPLAY=:0
export XAUTHORITY=/root/.Xauthority

# Install necessary tools
echo "Installing diagnostic tools..." | tee -a "$LOG_FILE"
sudo apt-get update -q
sudo apt-get install -y mesa-utils lshw pciutils glmark2 2>/dev/null

# System information
log "System Information" "uname -a"
log "CPU Information" "cat /proc/cpuinfo | grep -E 'model name|Hardware|processor|cpu cores|BogoMIPS'"
log "Memory Information" "free -h"

# GPU Information
log "GPU Information" "lshw -C display 2>/dev/null"
log "Loaded GPU Modules" "lsmod | grep -E 'mali|lima|gpu|drm'"
log "DRM Information" "cat /sys/class/drm/*/status 2>/dev/null || echo 'No DRM info available'"

# OpenGL/EGL Information
log "GLX Information" "DISPLAY=:0 glxinfo | grep -E 'direct|OpenGL vendor|OpenGL renderer'"
log "GL Extensions" "DISPLAY=:0 glxinfo | grep -E '^    GL_' | sort | uniq"

# Check GPU drivers
log "DRI Driver" "ls -la /usr/lib/*/dri/ | grep -E 'lima|mali'"

# Configuration files
log "X11 Configuration" "find /etc/X11 -type f -name '*.conf' -exec grep -l 'Device\\|Driver' {} \\; -exec cat {} \\;"

# Xorg log file
log "X Server Log" "cat /var/log/Xorg.0.log | grep -E 'lima|mali|DRM|AIGLX|GLX|EGL|GPU|rendering|direct'"

# Environmental variables
log "Environment Variables" "env | grep -E 'GL|MESA|DRM|RENDER|SDL'"

# Test OpenGL performance if glmark2 is available
if command -v glmark2 &>/dev/null; then
    log "Running basic OpenGL benchmark" "timeout 30s glmark2 --off-screen -s 800x600"
else
    echo "glmark2 not available for benchmarking" | tee -a "$LOG_FILE"
fi

echo "Diagnostics completed. Results saved to $LOG_FILE"
echo "Run 'cat $LOG_FILE' to see the full report"