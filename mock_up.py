import numpy as np
import sounddevice as sd
import serial
import time
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# -----------------------
# Configuration
# -----------------------
SAMPLE_RATE = 44100       # Audio sampling frequency
CHUNK = 1024              # Number of audio frames per FFT
DEVICE_INDEX = None       # Default audio input (set manually if needed)
SERIAL_PORT = '/dev/ttyACM0'  # Arduino serial port
BAUD_RATE = 115200

# -----------------------
# Serial Setup
# -----------------------
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)
    print(f"[OK] Connected to Arduino on {SERIAL_PORT}")
except Exception as e:
    print(f"[WARN] Could not connect to Arduino: {e}")
    ser = None

def send_to_arduino(bass, mid, treble):
    """Send simple RGB-style values to Arduino."""
    if ser:
        msg = f"{bass},{mid},{treble}\n"
        ser.write(msg.encode('utf-8'))

# -----------------------
# Audio and FFT Processing
# -----------------------
freqs = np.fft.rfftfreq(CHUNK, 1.0 / SAMPLE_RATE)
fft_bins = len(freqs)
fft_data = np.zeros(fft_bins)

# -----------------------
# Matplotlib Visualization Setup
# -----------------------
plt.style.use('dark_background')
fig, ax = plt.subplots(figsize=(10, 5))
bars = ax.bar(freqs, np.zeros_like(freqs), width=100)
ax.set_xlim(20, 12000)
ax.set_ylim(0, 2000)
ax.set_xscale('log')
ax.set_xlabel("Frequency (Hz)")
ax.set_ylabel("Magnitude")
ax.set_title("Live Audio Spectrum")

# -----------------------
# Audio Callback Function
# -----------------------
def audio_callback(indata, frames, time_info, status):
    global fft_data
    if status:
        print(status)

    # Convert stereo -> mono if needed
    audio_data = np.mean(indata, axis=1)

    # Compute FFT magnitude
    fft_vals = np.abs(np.fft.rfft(audio_data))
    fft_data = 0.6 * fft_data + 0.4 * fft_vals  # Smooth decay filter

    # Split into bands for lighting
    bass = np.mean(fft_vals[(freqs >= 20) & (freqs < 250)])
    mid = np.mean(fft_vals[(freqs >= 250) & (freqs < 4000)])
    treble = np.mean(fft_vals[(freqs >= 4000) & (freqs < 12000)])

    # Normalize and scale to 0–255
    def scale(x): return int(np.clip(x / 2000 * 255, 0, 255))
    bass, mid, treble = scale(bass), scale(mid), scale(treble)
    send_to_arduino(bass, mid, treble)

# -----------------------
# Animation Update Function
# -----------------------
def update_plot(frame):
    for bar, height in zip(bars, fft_data):
        bar.set_height(height)
    return bars

# -----------------------
# Run Audio Stream and Visualization
# -----------------------
try:
    stream = sd.InputStream(
        channels=1,
        samplerate=SAMPLE_RATE,
        blocksize=CHUNK,
        callback=audio_callback,
        device=DEVICE_INDEX
    )
    with stream:
        ani = animation.FuncAnimation(fig, update_plot, interval=30, blit=False)
        print("[RUNNING] Audio visualizer active — close the plot window to stop.")
        plt.show()

except KeyboardInterrupt:
    print("\n[STOP] Interrupted by user.")
except Exception as e:
    print(f"[ERROR] {e}")
finally:
    if ser:
        ser.close()
    print("[CLOSED] Serial connection terminated.")
