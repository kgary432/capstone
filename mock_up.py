import numpy as np
import sounddevice as sd
import serial
import time
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib import cm

# -----------------------
# Configuration
# -----------------------
SAMPLE_RATE = 44100
CHUNK = 1024
DEVICE_INDEX = None
SERIAL_PORT = '/dev/ttyACM0'
BAUD_RATE = 115200

# Beat detection parameters
ENERGY_HISTORY = 43     # Number of frames to average over (~1 sec)
BEAT_SENSITIVITY = 1.3  # Threshold multiplier

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

def send_to_arduino(bass, mid, treble, beat):
    """Send RGB + beat trigger to Arduino."""
    if ser:
        msg = f"{bass},{mid},{treble},{beat}\n"
        ser.write(msg.encode('utf-8'))

# -----------------------
# Audio and FFT Setup
# -----------------------
freqs = np.fft.rfftfreq(CHUNK, 1.0 / SAMPLE_RATE)
fft_data = np.zeros_like(freqs)
energy_history = [0] * ENERGY_HISTORY
last_beat_time = 0

# -----------------------
# Matplotlib Visualization Setup
# -----------------------
plt.style.use('dark_background')
fig, ax = plt.subplots(figsize=(10, 5))
bars = ax.bar(freqs, np.zeros_like(freqs), width=100, color='blue')

ax.set_xlim(20, 12000)
ax.set_ylim(0, 2500)
ax.set_xscale('log')
ax.set_xlabel("Frequency (Hz)")
ax.set_ylabel("Magnitude")
ax.set_title("Real-Time Audio Spectrum with Beat Detection")

# -----------------------
# Audio Callback
# -----------------------
def audio_callback(indata, frames, time_info, status):
    global fft_data, energy_history, last_beat_time

    if status:
        print(status)

    # Convert stereo to mono
    audio_data = np.mean(indata, axis=1)
    fft_vals = np.abs(np.fft.rfft(audio_data))
    fft_data = 0.6 * fft_data + 0.4 * fft_vals

    # Compute RMS energy
    energy = np.sqrt(np.mean(audio_data ** 2))
    energy_history.append(energy)
    if len(energy_history) > ENERGY_HISTORY:
        energy_history.pop(0)

    # Beat detection (simple adaptive threshold)
    avg_energy = np.mean(energy_history)
    beat_detected = energy > BEAT_SENSITIVITY * avg_energy

    # Split frequency bands
    bass = np.mean(fft_vals[(freqs >= 20) & (freqs < 250)])
    mid = np.mean(fft_vals[(freqs >= 250) & (freqs < 4000)])
    treble = np.mean(fft_vals[(freqs >= 4000) & (freqs < 12000)])

    # Normalize 0–255
    def scale(x): return int(np.clip(x / 2000 * 255, 0, 255))
    bass, mid, treble = scale(bass), scale(mid), scale(treble)

    # Send beat signal (1 if beat detected)
    send_to_arduino(bass, mid, treble, int(beat_detected))

# -----------------------
# Visualization Update
# -----------------------
def update_plot(frame):
    # Color map intensity by magnitude
    norm = plt.Normalize(0, np.max(fft_data) + 1)
    colors = cm.plasma(norm(fft_data))
    for bar, height, c in zip(bars, fft_data, colors):
        bar.set_height(height)
        bar.set_color(c)

    # Flash background briefly if beat detected
    avg_energy = np.mean(energy_history)
    current_energy = energy_history[-1]
    if current_energy > BEAT_SENSITIVITY * avg_energy:
        fig.patch.set_facecolor('#440154')  # Bright purple flash
    else:
        fig.patch.set_facecolor('black')

    return bars

# -----------------------
# Run the Stream + Visualization
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
        print("[RUNNING] Visualizer active — close window to stop.")
        plt.show()

except KeyboardInterrupt:
    print("\n[STOP] Interrupted by user.")
except Exception as e:
    print(f"[ERROR] {e}")
finally:
    if ser:
        ser.close()
    print("[CLOSED] Serial connection terminated.")
