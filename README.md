# Reactive Companion System

A modular Python-based reactive companion system optimized for small single-board computers.

## Overview

This system uses three communicating processes via ZeroMQ:

1. **Awareness Node** - Monitors environment via audio/video
2. **Brains Node** - Processes triggers and generates responses
3. **UI Node** - Provides visual feedback and interaction

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

## Project Structure

- **awareness**: Environmental monitoring and trigger detection
- **brains**: Core processing and response generation 
- **ui**: Pygame-based user interface
- **common**: Shared utilities and messaging infrastructure
