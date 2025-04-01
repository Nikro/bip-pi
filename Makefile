.PHONY: install test lint format update clean run-ui run-awareness run-brains pygame-setup

# Installation and setup
install:
    poetry install

# PyGame setup specific for the UI component
pygame-setup:
    pip install pygame
    @echo "PyGame installed successfully"

# Testing
test:
    poetry run pytest

# Code quality
lint:
    poetry run flake8 src tests
    poetry run mypy src tests

format:
    poetry run black src tests
    poetry run isort src tests

# Update system
update: install pygame-setup
    @echo "System updated successfully"

# Running components
run-ui:
    poetry run python -m src.ui.ui --config=config/ui_config.json

run-awareness:
    poetry run python -m src.awareness.awareness --config=config/awareness_config.json

run-brains:
    poetry run python -m src.brains.brains --config=config/brains_config.json

# Cleanup
clean:
    rm -rf .pytest_cache .coverage htmlcov .mypy_cache
    find . -type d -name __pycache__ -exec rm -rf {} +