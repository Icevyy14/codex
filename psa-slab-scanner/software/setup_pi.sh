#!/usr/bin/env bash
# SlabRail Raspberry Pi setup: Pi 5 (4 GB), Raspberry Pi OS Bookworm 64-bit, Python 3.11.
# Run it from the software/ folder as your normal user (it calls sudo itself):
#     bash setup_pi.sh            # add --service to also start the web page at boot
# Safe to run again.
set -euo pipefail
cd "$(dirname "$0")"
SERVICE=0
[[ "${1:-}" == "--service" ]] && SERVICE=1

echo "== apt packages"
sudo apt-get update
# picamera2 from apt (the Raspberry Pi docs' way); --no-install-recommends keeps the GUI preview bits off a Lite image
sudo apt-get install -y --no-install-recommends python3-picamera2
sudo apt-get install -y python3-venv python3-numpy python3-opencv python3-flask python3-serial python3-gpiozero \
    python3-pil python3-packaging tesseract-ocr i2c-tools v4l-utils
# gpiozero on a Pi 5 needs lgpio (RPi.GPIO does not work on the Pi 5); normally already installed
sudo apt-get install -y python3-lgpio || echo "WARNING: python3-lgpio not installed - gpiozero may not drive the Pi 5 GPIO"

echo "== I2C (ADS1115 vacuum sensor ADC)"
# raspi-config's non-interactive mode uses 0 = ENABLE
sudo raspi-config nonint do_i2c 0 || echo "WARNING: could not enable I2C - use sudo raspi-config > Interface Options > I2C"

echo "== groups: serial (controller), i2c, video (cameras), gpio"
sudo usermod -aG dialout,i2c,video,gpio "$USER" || sudo usermod -aG dialout,i2c,video "$USER"

echo "== Python venv (sees the apt packages)"
python3 -m venv --system-site-packages .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/python -c "import picamera2, cv2, numpy, zxingcpp, flask, serial, gpiozero, smbus2; print('imports OK: numpy', numpy.__version__, '| OpenCV', cv2.__version__)"

echo "== machine config from the CAD layout"
.venv/bin/python -m tools.gen_config

if [[ $SERVICE == 1 ]]; then
  echo "== systemd service: web page on port 8080 at boot"
  sudo tee /etc/systemd/system/slabrail-web.service >/dev/null <<UNIT
[Unit]
Description=SlabRail web page
After=network-online.target

[Service]
User=$USER
WorkingDirectory=$PWD
# Tesseract OCR: one OpenMP thread. With the default threads OCR timed out on a busy CPU (slabscan/decode.py sets it too)
Environment=OMP_THREAD_LIMIT=1
ExecStart=$PWD/.venv/bin/python -m slabscan web --port 8080
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT
  sudo systemctl daemon-reload
  sudo systemctl enable --now slabrail-web.service
fi

cat <<NEXT

Done. REBOOT now (I2C and the new groups need it):  sudo reboot
Then, from $(pwd):
  source .venv/bin/activate
  ls /dev/i2c-1 && i2cdetect -y 1          # the ADS1115 should show at 48
  rpicam-hello --list-cameras              # the Camera Module 3 (station camera)
  v4l2-ctl --list-devices                  # the USB head camera (NOT /dev/video0 on a Pi 5)
  python -m slabscan selftest -i           # every part, with hand checks
NEXT
