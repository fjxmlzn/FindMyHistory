#!/bin/bash

# Set variables
SCRIPT_DIR="CHANGE/ME/TO/REPO/PATH"
VENV_DIR="${SCRIPT_DIR}/venv"
REQUIREMENTS_FILE="${SCRIPT_DIR}/requirements.txt"

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "Created virtual environment at $VENV_DIR"
else
    echo "Virtual environment already exists at $VENV_DIR"
fi

# Activate virtual environment
source "${VENV_DIR}/bin/activate"

# Upgrade pip
pip install --upgrade pip

# Install or upgrade requirements
if [ -f "$REQUIREMENTS_FILE" ]; then
    pip install -r "$REQUIREMENTS_FILE" --upgrade
    echo "Installed/upgraded packages from $REQUIREMENTS_FILE"
else
    echo "Requirements file not found at $REQUIREMENTS_FILE"
    exit 1
fi

echo "Setup complete!"