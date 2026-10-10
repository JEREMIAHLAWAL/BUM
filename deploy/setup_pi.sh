#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "=== Setting up BUM Agent Flow Control Room ==="
echo "Working directory: $SCRIPT_DIR"

# 1. Create Python virtual environment if not present
if [ ! -f ".venv/bin/activate" ]; then
    echo "Creating clean virtual environment (.venv)..."
    rm -rf .venv
    python3 -m venv .venv
fi

# 2. Activate and install dependencies
echo "Installing Python dependencies..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 3. Check for .env file
if [ ! -f ".env" ]; then
    echo "[WARN] No .env file found in $SCRIPT_DIR."
    echo "Copying .env.example to .env..."
    cp .env.example .env
    echo "Please configure your API keys in .env."
else
    echo "[OK] .env file found."
fi

# 4. Check for pre-built UI assets
if [ ! -d "agent-flow-ui/dist" ]; then
    echo "[INFO] UI dist bundle not found. Building with npm..."
    if command -v npm &> /dev/null; then
        cd agent-flow-ui
        npm install
        npm run build
        cd ..
    else
        echo "[ERROR] npm is not installed and agent-flow-ui/dist is missing."
        exit 1
    fi
else
    echo "[OK] agent-flow-ui/dist assets found."
fi

echo ""
echo "=== Setup Complete ==="
echo "To test run manually:"
echo "    source .venv/bin/activate && python run_server.py"
echo ""
echo "To enable 24/7 background systemd service:"
echo "    sudo cp deploy/bum-agent-flow.service /etc/systemd/system/"
echo "    sudo systemctl daemon-reload"
echo "    sudo systemctl enable --now bum-agent-flow"
echo "=================================================="
