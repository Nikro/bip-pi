# Reactive Companion System

A modular Python-based reactive companion system optimized for small single-board computers.

## Overview

This system uses three communicating processes via ZeroMQ:

1. **Awareness Node** - Monitors environment via audio/video
2. **Brains Node** - Processes triggers and generates responses
3. **UI Node** - Provides visual feedback and interaction

## Quick Demo

Try the system demonstration without hardware requirements:

```bash
# Quick 15-second demo
make demo-short

# Full 30-second demo  
make demo

# Verbose demo with detailed logging
make demo-verbose

# Or run directly with custom duration
poetry run python demo.py --duration 60
```

The demo simulates audio triggers and shows how the system processes them through different states.

## Installation

Setup is simple with our all-in-one installation script:

```bash
git clone <this-repo-url>
cd reactive-companion
chmod +x install.sh
./install.sh
```

This will:
1. Set up a lightweight GUI environment (OpenBox)
2. Configure auto-login and display
3. Create the project structure
4. Set up Python environment with Poetry
5. Configure SSH for local network access only

### Manual Installation

If you prefer manual setup:

```bash
# Install Poetry and dependencies
pip install poetry
poetry install

# Add missing audio/graphics libraries (if needed)
poetry add sounddevice PyOpenGL PyOpenGL_accelerate

# Install system dependencies (Ubuntu/Debian)
sudo apt-get install portaudio19-dev
```

## Using the System

After installation, you can run the components:

```bash
# The environment is automatically activated
cd ~/reactive-companion

# Start the UI
python -m src.ui.ui

# In separate terminals:
python -m src.awareness.awareness
python -m src.brains.brains
```

### Using Make Commands

```bash
# Start individual components
make run-ui
make run-awareness  
make run-brains

# Development commands
make test           # Run tests
make lint          # Code quality checks
make format        # Auto-format code
```

## Project Structure

- **awareness**: Environmental monitoring and trigger detection
- **brains**: Core processing and response generation 
- **ui**: Pygame-based user interface with OpenGL acceleration
- **common**: Shared utilities and messaging infrastructure
- **demo.py**: Standalone demonstration script
