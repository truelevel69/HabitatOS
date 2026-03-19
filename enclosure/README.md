# Pixie Frog Enclosure Monitor

Raspberry Pi 5 environmental monitoring system for an African Pixie Frog enclosure.
Reads temperature and humidity from a DHT11 sensor, controls 4 relay channels,
logs all readings to a local SQLite database, and serves a touchscreen dashboard
with an animated idle screen.

---

## Hardware

| Component              | Connection                          |
|------------------------|-------------------------------------|
| DHT11 data pin         | GPIO4 (BCM) + 10kΩ pull-up to 3.3V |
| DHT11 VCC              | 3.3V pin                            |
| DHT11 GND              | GND pin                             |
| Relay channel 1 (IN1)  | GPIO17 — Grow light                 |
| Relay channel 2 (IN2)  | GPIO18 — Heat lamp                  |
| Relay channel 3 (IN3)  | GPIO27 — Misting pump               |
| Relay channel 4 (IN4)  | GPIO22 — Circulation fan            |
| Relay VCC              | 5V pin                              |
| Relay GND              | GND pin                             |
| 7″ touchscreen         | DSI ribbon (display) + USB-A (touch)|

**Note:** Most 4-channel relay boards are active-low — the code accounts for this.
GPIO LOW = relay ON, GPIO HIGH = relay OFF.

---

## File structure

```
enclosure/
├── app.py                  # Main Flask app, sensor loop, relay control, SQLite logging
├── requirements.txt        # Python dependencies
├── install.sh              # One-time setup script
├── enclosure.db            # Auto-created on first run — SQLite database
├── static/
│   └── frogidle.gif        # Idle screen background animation
└── templates/
    └── index.html          # Touchscreen dashboard (served by Flask)
```

---

## First-time setup

1. Flash Raspberry Pi OS (64-bit, with desktop) to a microSD card using Raspberry Pi Imager.
2. Boot the Pi, connect to WiFi, open a terminal.
3. Copy this folder to the Pi (USB drive, `scp`, or just retype/download).
4. Run the install script:

```bash
cd enclosure
chmod +x install.sh
./install.sh
```

5. Reboot. The monitor app starts automatically, and Chromium opens fullscreen to the dashboard.

---

## Manual run (for testing)

```bash
cd enclosure
python3 app.py
```

Then open a browser to `http://localhost:5000`.

From another device on the same WiFi network, browse to `http://<your-pi-ip>:5000`.

---

## Idle screen

After `IDLE_TIMEOUT_SECONDS` of no touch activity (default: 120s), the dashboard fades
into the idle screen — a full-screen animated GIF with the current time, temp/humidity,
and relay status dots overlaid. Tap anywhere to wake back to the dashboard.

To change the timeout, edit `IDLE_TIMEOUT_SECONDS` at the top of `app.py`.

---

## Useful commands

```bash
# Check if the service is running
sudo systemctl status enclosure-monitor

# View live logs
sudo journalctl -u enclosure-monitor -f

# Restart after making code changes
sudo systemctl restart enclosure-monitor

# Find your Pi's IP address
hostname -I
```

---

## Sensor ranges (African Pixie Frog)

| Reading     | Ideal range |
|-------------|-------------|
| Temperature | 75–85°F     |
| Humidity    | 60–80%      |

These are set in `app.py` at the top — change `TEMP_MIN_F`, `TEMP_MAX_F`,
`HUM_MIN`, and `HUM_MAX` to adjust the warning thresholds.

---

## Simulated mode

If `app.py` is run on a non-Pi computer (Windows/Mac), it automatically
detects that GPIO and DHT11 aren't available and simulates slowly drifting
sensor values. Useful for testing the dashboard UI without hardware.
