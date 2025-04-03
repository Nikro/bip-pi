#!/bin/bash
# This script updates the repository, validates the environment, and starts the application

# Redirect all output to a log file so we can fetch the most recent run logs later.
exec >> "$(dirname "$(readlink -f "$0")")/logs/update_and_run.log" 2>&1

# Script constants
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
REQUIRED_FILES=(".env" "config/ui_config.json" "config/awareness_config.json" "config/brains_config.json")
MISSING_FILES=()
ERROR_LOG="${SCRIPT_DIR}/logs/startup_errors.log"

# Set PyGame optimization flags before any Python scripts are run
export PYGAME_DETECT_AVX2=1
export PYGAME_HIDE_SUPPORT_PROMPT=1

# Create logs directory if it doesn't exist
mkdir -p "${SCRIPT_DIR}/logs"

# Function to log messages to console and log file
log_message() {
    local level="$1"
    local message="$2"
    local timestamp
    timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    
    echo "[$level] $message"
    echo "[$timestamp] [$level] $message" >> "$ERROR_LOG"
}

# Check if this is the first run after installation
if [ ! -f "${SCRIPT_DIR}/.first_run_complete" ]; then
    log_message "INFO" "First run detected. Performing additional setup..."
    
    # Try to ensure all required libraries are installed
    if [ -x "$(command -v apt-get)" ]; then
        log_message "INFO" "Installing required development libraries..."
        sudo apt-get install -y libffi-dev build-essential python3-dev
        
        # Install PyGame for better performance - make sure to use the system version
        log_message "INFO" "Installing PyGame for improved performance..."
        
        if [ -f ".venv/bin/activate" ]; then
            source .venv/bin/activate
            pip install --upgrade pygame
        elif command -v poetry &>/dev/null; then
            poetry add pygame
        else
            log_message "WARNING" "Neither virtual environment nor Poetry found. Cannot install PyGame."
        fi
        
        # Create marker file to avoid repeating this step
        touch "${SCRIPT_DIR}/.first_run_complete"
    fi
fi

# Function to check for required files
check_required_files() {
    log_message "INFO" "Checking for required configuration files..."
    
    for file in "${REQUIRED_FILES[@]}"; do
        if [ ! -f "${SCRIPT_DIR}/$file" ]; then
            MISSING_FILES+=("$file")
            log_message "ERROR" "Missing required file: $file"
        fi
    done
}

# Change to script directory
cd "$SCRIPT_DIR" || {
    log_message "ERROR" "Failed to change to script directory: $SCRIPT_DIR"
    exit 1
}

log_message "INFO" "Starting update process at $(date)"

# Pull latest changes from Git repository
log_message "INFO" "Pulling latest changes from Git..."
if ! git pull; then
    log_message "WARNING" "Git pull failed. Continuing with existing code."
fi

# Check for required files before proceeding
check_required_files

# Check if there are missing files
if [ ${#MISSING_FILES[@]} -gt 0 ]; then
    log_message "ERROR" "Cannot start application due to missing required files:"
    for file in "${MISSING_FILES[@]}"; do
        log_message "ERROR" "  - $file"
    done
    
    # Display graphical error if DISPLAY is available
    if [ -n "$DISPLAY" ]; then
        if command -v zenity &>/dev/null; then
            zenity --error --title="Reactive Companion Error" --text="Missing required configuration files:\n$(printf '  - %s\n' "${MISSING_FILES[@]}")"
        elif command -v notify-send &>/dev/null; then
            notify-send -u critical "Reactive Companion Error" "Missing configuration files. Check logs for details."
        fi
    fi
    
    # Keep the terminal window open with the error message
    echo ""
    echo "Press Enter to exit..."
    read -r
    exit 1
fi

# Try to activate the Python environment
log_message "INFO" "Activating Python environment..."

# Detect and configure hardware acceleration
detect_hardware_acceleration() {
    log_message "INFO" "Detecting hardware acceleration capabilities..."
    
    # Variables to track hardware acceleration status
    local has_lima=0
    local has_mali=0
    
    # Check for Lima/Mali400 driver in kernel modules
    if lsmod | grep -q -E 'lima|mali|gpu_sched|drm_shmem_helper' 2>/dev/null; then
        log_message "INFO" "Lima/Mali GPU driver detected"
        has_lima=1
    fi
    
    # Check for specific Mali400 hardware on Allwinner SoCs
    if grep -q -E "Allwinner|sun8i" /proc/cpuinfo 2>/dev/null || 
       grep -q -E "Allwinner|sun8i" /proc/device-tree/compatible 2>/dev/null; then
        log_message "INFO" "Allwinner SoC with Mali400 GPU detected"
        has_mali=1
    fi
    
    # Set minimal environment variables for hardware acceleration
    export SDL_VIDEODRIVER="x11"  # Use X11 driver for best compatibility
    export PYGAME_DISPLAY=:0      # Ensure display is set
    
    # Only set hardware-specific variables if Mali/Lima GPU is detected
    if [ $has_lima -eq 1 ] || [ $has_mali -eq 1 ]; then
        log_message "INFO" "Enabling Mali400/Lima GPU optimizations"
        
        # Use hardware acceleration in PyGame
        export PYGAME_HWSURFACE=1
        export PYGAME_DOUBLEBUF=1
        export PYGAME_DETECT_AVX2=1
        
        # Texture filtering - nearest is faster on Mali400
        export SDL_HINT_RENDER_SCALE_QUALITY="0"
    fi
}

# Detect and configure hardware acceleration
detect_hardware_acceleration

# Activate virtual environment FIRST, then check for poetry
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    log_message "INFO" "Virtual environment activated: $(which python)"
    log_message "INFO" "Python version: $(python --version 2>&1)"
    
    # Now check if Poetry is available (after activating the environment)
    if command -v poetry &>/dev/null; then
        log_message "INFO" "Poetry found in virtual environment, using it to run application..."
        
        # Update dependencies if needed
        if ! poetry install; then
            log_message "WARNING" "Poetry install failed. Continuing with existing dependencies."
        fi
        
        # Run the UI application with Poetry
        log_message "INFO" "Starting UI application with Poetry..."
        poetry run python -m src.ui.ui
        
        exit_code=$?
        log_message "INFO" "UI application exited with code $exit_code at $(date)"
    else
        # Poetry not found even after activation, use direct Python
        log_message "INFO" "Poetry not found in virtual environment. Using Python directly..."
        
        # Ensure pygame is installed
        if ! python -c "import pygame" 2>/dev/null; then
            log_message "WARNING" "PyGame not found in virtual environment. Attempting to install..."
            pip install pygame
        fi
        
        # Start the UI application directly
        log_message "INFO" "Starting UI application with Python..."
        python -m src.ui.ui
        
        exit_code=$?
        log_message "INFO" "UI application exited with code $exit_code at $(date)"
    fi
else
    log_message "ERROR" "No virtual environment found. Cannot start application."
    
    # Display graphical error if possible
    if [ -n "$DISPLAY" ] && command -v zenity &>/dev/null; then
        zenity --error --title="Reactive Companion Error" --text="No Python virtual environment found.\nPlease run the installation script first."
    fi
    
    echo ""
    echo "Press Enter to exit..."
    read -r
    exit 1
fi

# Keep terminal window open briefly to show any exit messages
sleep 3