#!/bin/bash
# filepath: /var/www/bip-pi/update_and_run.sh
# This script updates the repository, validates the environment, and starts the application

# Script constants
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
REQUIRED_FILES=(".env" "config/ui_config.json" "config/awareness_config.json" "config/brains_config.json")
MISSING_FILES=()
ERROR_LOG="${SCRIPT_DIR}/logs/startup_errors.log"

# Create logs directory if it doesn't exist
mkdir -p "${SCRIPT_DIR}/logs"

# Function to log messages to console and log file
log_message() {
    local level="$1"
    local message="$2"
    local timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    
    echo "[$level] $message"
    echo "[$timestamp] [$level] $message" >> "$ERROR_LOG"
}

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

# Check for Poetry first
if command -v poetry &>/dev/null; then
    log_message "INFO" "Using Poetry to run the application..."
    
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
    # Fallback to direct virtual environment activation
    log_message "INFO" "Poetry not found. Using virtual environment directly..."
    
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
        
        # Start the UI application directly
        log_message "INFO" "Starting UI application with Python..."
        python -m src.ui.ui
        
        exit_code=$?
        log_message "INFO" "UI application exited with code $exit_code at $(date)"
    else
        log_message "ERROR" "No virtual environment found. Cannot start application."
        
        # Display error graphically if possible
        if [ -n "$DISPLAY" ] && command -v zenity &>/dev/null; then
            zenity --error --title="Reactive Companion Error" --text="No Python virtual environment found.\nPlease run the installation script first."
        fi
        
        echo ""
        echo "Press Enter to exit..."
        read -r
        exit 1
    fi
fi

# Keep terminal window open briefly to show any exit messages
sleep 3