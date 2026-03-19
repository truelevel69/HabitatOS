#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# Pixie Frog Enclosure Monitor — Setup Script
# Run once after flashing Raspberry Pi OS:
#   chmod +x install.sh && ./install.sh
# ─────────────────────────────────────────────────────────────────

set -e
echo ""
echo "  Pixie Frog Enclosure Monitor — Setup"
echo "─────────────────────────────────────────"

# Update system
echo "[1/5] Updating system packages..."
sudo apt-get update -y && sudo apt-get upgrade -y

# Install Python dependencies
echo "[2/5] Installing Python libraries..."
pip3 install --break-system-packages -r requirements.txt

# Install Chromium (usually already present on Pi OS with desktop)
echo "[3/5] Ensuring Chromium is installed..."
sudo apt-get install -y chromium-browser

# Create a systemd service so the app starts on boot
echo "[4/5] Creating systemd service..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sudo tee /etc/systemd/system/enclosure-monitor.service > /dev/null <<EOF
[Unit]
Description=Pixie Frog Enclosure Monitor
After=network.target

[Service]
ExecStart=/usr/bin/python3 $SCRIPT_DIR/app.py
WorkingDirectory=$SCRIPT_DIR
StandardOutput=journal
StandardError=journal
Restart=always
RestartSec=5
User=$USER

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable enclosure-monitor.service

# Create a kiosk autostart entry so Chromium opens fullscreen on boot
echo "[5/5] Setting up kiosk autostart..."
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/enclosure-kiosk.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Enclosure Kiosk
Exec=bash -c "sleep 8 && chromium-browser --kiosk --noerrdialogs --disable-infobars --no-first-run http://localhost:5000/boot"
EOF

echo ""
echo "  Done! Reboot to start everything automatically."
echo ""
echo "  Manual commands:"
echo "    Start the app now:  sudo systemctl start enclosure-monitor"
echo "    View logs:          sudo journalctl -u enclosure-monitor -f"
echo "    Stop the app:       sudo systemctl stop enclosure-monitor"
echo "    Web dashboard:      http://localhost:5000/boot  (or your Pi's IP on LAN)"
echo ""
