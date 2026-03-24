#!/bin/bash
# CI/CD Agent - Linux/macOS Initialization Script

set -e

echo ""
echo "========================================"
echo "CI/CD Agent Setup"
echo "========================================"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo ""
    echo "NOTE: Edit .env and add your GROQ_API_KEY"
    echo "Get it from: https://console.groq.com/keys"
    echo ""
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found. Please install Python 3.9+"
    exit 1
fi

echo "Python: $(python3 --version)"

# Create venv if needed
if [ ! -d venv ]; then
    echo ""
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

echo ""
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo ""
echo "To test the pipeline, run:"
echo "  python test_pipeline.py"
echo ""
