#!/usr/bin/env bash
# ==============================================================================
# INDIGO QUANT — Raspberry Pi 4 / Debian Linux Deployment Script
# Configures headless 24/7 background operation with persistent storage,
# systemd auto-restart, and local network dashboard access.
# ==============================================================================

set -euo pipefail

echo "=========================================================="
echo "   INDIGO QUANT — RASPBERRY PI 4 DEPLOYMENT SETUP"
echo "=========================================================="

# 1. Verify Python Version (>= 3.11)
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed. Installing python3, python3-venv, and build-essential..."
    sudo apt update && sudo apt install -y python3 python3-venv python3-pip build-essential libatlas-base-dev
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Detected Python $PY_VER"

# 2. Setup Virtual Environment
INSTALL_DIR=$(pwd)
echo "Setting up virtual environment in $INSTALL_DIR/.venv..."
python3 -m venv .venv
source .venv/bin/activate

# 3. Upgrade Pip and Install Dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install -e . --no-deps

# 4. Initialize Database
python3 -c "from indigo_quant.db.session import SessionLocal; from indigo_quant.db.repository import init_db, seed_universe_and_accounts; init_db(); db = SessionLocal(); seed_universe_and_accounts(db); db.close()"
echo "Database and 5 virtual portfolios initialized."

# 5. Configure Systemd Service
SERVICE_FILE="/etc/systemd/system/indigo-quant.service"
CURRENT_USER=$(whoami)

echo "Generating systemd service file..."
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Indigo Quant Autonomous Swing-Trading Research Engine
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/.venv/bin/streamlit run src/indigo_quant/dashboard/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
Restart=always
RestartSec=10
StandardOutput=append:$INSTALL_DIR/logs/indigo.log
StandardError=append:$INSTALL_DIR/logs/indigo_error.log

[Install]
WantedBy=multi-user.target
EOF

mkdir -p "$INSTALL_DIR/logs"

sudo systemctl daemon-reload
echo "Systemd unit installed at $SERVICE_FILE"

echo "=========================================================="
echo "DEPLOYMENT COMPLETE!"
echo "=========================================================="
echo "To enable and start the service on boot:"
echo "  sudo systemctl enable --now indigo-quant"
echo ""
echo "To check service status:"
echo "  sudo systemctl status indigo-quant"
echo ""
echo "To access the dashboard from any computer on your local WiFi/LAN:"
echo "  http://$(hostname -I | awk '{print $1}'):8501"
