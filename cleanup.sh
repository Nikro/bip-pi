#!/bin/bash
# filepath: /var/www/bip-pi/cleanup.sh
# Script to clean up unused files and directories

SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
cd "$SCRIPT_DIR"

echo "==> Starting cleanup process..."

# Clean Python cache files
echo "Cleaning Python cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete
find . -name "*.pyo" -delete

# Remove any temp files
echo "Removing temporary files..."
find . -name "*~" -delete
find . -name ".*.swp" -delete

# Clean up any potential leftover log files
if [ -d "logs" ]; then
  echo "Cleaning old log files..."
  find logs -name "*.log" -type f -mtime +7 -delete
fi

echo "==> Cleanup complete!"