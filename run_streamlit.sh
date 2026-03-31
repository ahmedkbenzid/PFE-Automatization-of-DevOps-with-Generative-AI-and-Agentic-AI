#!/bin/bash
# Quick Start Script for Streamlit DevOps Orchestrator
# Unix/Linux/MacOS Shell Script

set -e  # Exit on error

echo "================================================"
echo " Multi-Agent DevOps Orchestrator - Quick Start"
echo "================================================"
echo

# Check Python installation
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed or not in PATH"
    echo "Please install Python 3.9+ from https://www.python.org/downloads/"
    exit 1
fi

echo "[1/5] Checking Python installation..."
python3 --version
echo

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "[2/5] Creating virtual environment..."
    python3 -m venv venv
else
    echo "[2/5] Virtual environment already exists"
fi
echo

# Activate virtual environment
echo "[3/5] Activating virtual environment..."
source venv/bin/activate
echo

# Install dependencies
echo "[4/5] Installing Streamlit dependencies..."
pip install -r streamlit-requirements.txt --quiet || echo "[WARNING] Some dependencies failed to install"
echo

# Install agent dependencies
echo "Installing agent dependencies..."
cd test_pfe/02-orchestration-agents-layer/orchestrator-agent
pip install -r requirements.txt --quiet || true
cd ../../..

cd test_pfe/02-orchestration-agents-layer/cicd-agent
pip install -r requirements.txt --quiet || true
cd ../../..

cd test_pfe/02-orchestration-agents-layer/docker-agent
pip install -r requirements.txt --quiet || true
cd ../../..

echo

# Check for .env file
if [ ! -f ".env" ]; then
    echo "[WARNING] .env file not found!"
    echo
    echo "Creating template .env file..."
    cat > .env << EOF
# Multi-Agent DevOps Orchestrator Configuration
#
# Required: GROQ API Key
GROQ_API_KEY=your_groq_api_key_here

# Optional: GitHub Token for PR creation
GITHUB_TOKEN=

# Optional: LLM Configuration
LLM_PROVIDER=ollama
OLLAMA_MODEL=glm-5:cloud
LLM_TEMPERATURE=0.3
LLM_MAX_TOKENS=3000
EOF
    echo
    echo "[ACTION REQUIRED] Please edit .env file and add your GROQ_API_KEY"
    echo "Get your API key from: https://console.groq.com"
    echo
    read -p "Press Enter to continue after updating .env file..."
fi

# Launch Streamlit
echo "[5/5] Launching Streamlit app..."
echo
echo "================================================"
echo " Opening browser at http://localhost:8501"
echo " Press Ctrl+C to stop the server"
echo "================================================"
echo

streamlit run app.py
