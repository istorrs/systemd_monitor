#!/bin/bash
# Development environment setup script
# Run this after cloning the repository

set -e

echo "Setting up systemd_monitor development environment..."
echo ""

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python version: $python_version"

# Install development dependencies
echo ""
echo "Installing development dependencies..."
pip3 install --upgrade pip setuptools wheel

# Install pre-commit framework
echo ""
echo "Installing pre-commit framework..."
pip3 install pre-commit

# Install pre-commit hooks
echo ""
echo "Installing git hooks..."
pre-commit install

# Install package dependencies
echo ""
echo "Installing package dependencies..."
if [ -f requirements-ci.txt ]; then
    pip3 install -r requirements-ci.txt
fi

# Install the package in development mode
echo ""
echo "Installing systemd_monitor in development mode..."
pip3 install -e .

echo ""
echo "✓ Development environment setup complete!"
echo ""
echo "Pre-commit hooks installed. They will run automatically on 'git commit'."
echo "To manually run hooks on all files: pre-commit run --all-files"
