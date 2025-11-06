#!/bin/bash
# ============================================
# Raspberry Pi 5 Audio-Reactive Lighting Setup
# ============================================

echo "Starting setup for Raspberry Pi reactive lighting project..."

# -----------------------
# System Updates
# -----------------------
echo "Updating system..."
sudo apt update && sudo apt upgrade -y

# -----------------------
# Install Dependencies
# -----------------------
echo "Installing Python and required libraries..."
sudo apt install -y python3 python3-pip python3-tk portaudio19-dev
pip install --upgrade pip
pip install numpy sounddevice matplotlib pyserial

# -----------------------
# Setup Project Directory
# -----------------------
PROJECT_DIR="/home/pi/reactive_lights"
echo "Creating project directory at $PROJECT_DIR"
mkdir -p $PROJECT_DIR

# -----------------------
# Copy Main Python Script
# -----------------------
SCRIPT_NAME="audio_fft_visualizer_beat_to_arduino.py"

if [ -f "$SCRIPT_NAME" ]; then
    echo "📄 Copying $SCRIPT_NAME to $PROJECT_DIR"
    cp "$SCRIPT_NAME" "$PROJECT_DIR/"
else
    echo "Could not find $SCRIPT_NAME in current directory."
    echo "Please make sure the script is in the same folder as this setup file."
fi

# -----------------------
# Enable Serial and Audio Access
# -----------------------
echo "Configuring user permissions for serial and audio..."
sudo usermod -a -G dialout $USER
sudo usermod -a -G audio $USER

# -----------------------
# Done
# -----------------------
echo ""
echo "Setup complete!"
echo "You can now run the program manually with:"
echo "   python3 $PROJECT_DIR/$SCRIPT_NAME"
echo ""
echo "When it starts, you'll see the live FFT visualizer window and reactive LEDs!"
