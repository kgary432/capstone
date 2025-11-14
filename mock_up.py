import numpy as np
import sounddevice as sd
import time
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from collections import deque
import threading

# Shared data storage for thread-safe access
# Threading is necessary because:
# - analyze_audio() runs in sounddevice's audio callback thread (called ~43 times/sec)
# - update_plot() runs in matplotlib's animation thread (called ~20 times/sec)
# Both threads access the same shared data (bass_history, etc.), so we need a lock
# to prevent race conditions where one thread reads while the other writes
data_lock = threading.Lock()
bass_history = deque(maxlen=200)
mid_history = deque(maxlen=200)
treble_history = deque(maxlen=200)
beat_flags = deque(maxlen=200)      # Track beats for visualization
recent_bass = deque(maxlen=20)      # Keep last 20 bass values for beat detection
sample_counter = 0                 # Continuously incrementing sample counter (not tied to deque length)
last_beat_sample = -1               # Track when last beat was detected (sample index)
first_sample_in_window = 0          # Track the sample counter value of the first item in the history deques
BEAT_COOLDOWN = 15                  # Minimum samples between beats (prevents multiple detections per beat)

def analyze_audio(indata, frames, time_info, status):
    global last_beat_sample, sample_counter, first_sample_in_window
    
    # Check for audio input level (RMS)
    rms_level = np.sqrt(np.mean(indata**2))
    
    samples = indata[:, 0]
    fft = np.abs(np.fft.rfft(samples))
    freqs = np.fft.rfftfreq(len(samples), 1/44100)

    bass = np.mean(fft[(freqs >= 20) & (freqs < 250)])
    mid = np.mean(fft[(freqs >= 250) & (freqs < 4000)])
    treble = np.mean(fft[(freqs >= 4000) & (freqs < 16000)])
    
    # Simple beat detection: compare current bass to recent average
    with data_lock:
        recent_bass.append(bass)
        sample_counter += 1
        
        # Track when the history window wraps around (when deque is full and we're about to append)
        was_full = len(bass_history) == bass_history.maxlen
        
        # Beat detection: current bass must be 1.5x above recent average AND cooldown must have passed
        beat = 0
        if len(recent_bass) >= 5:
            recent_avg = np.mean(list(recent_bass)[:-1])  # Average excluding current value
            samples_since_last_beat = sample_counter - last_beat_sample
            
            # Ensure last_beat_sample doesn't get too far behind (reset if it's way outside the window)
            # This prevents issues after the window wraps around multiple times
            if last_beat_sample > 0 and samples_since_last_beat > bass_history.maxlen * 2:
                last_beat_sample = sample_counter - BEAT_COOLDOWN  # Reset to allow immediate beat detection
                samples_since_last_beat = BEAT_COOLDOWN  # Recalculate after reset
            
            if bass > recent_avg * 1.5 and samples_since_last_beat >= BEAT_COOLDOWN:
                beat = 1
                last_beat_sample = sample_counter
        
        # Store values for visualization
        bass_history.append(bass)
        mid_history.append(mid)
        treble_history.append(treble)
        beat_flags.append(beat == 1)
        
        # If the deque was full and we just added a new item, the oldest was removed
        # Update first_sample_in_window to track the new first item
        if was_full:
            first_sample_in_window = sample_counter - bass_history.maxlen + 1
        elif sample_counter == 1:
            first_sample_in_window = 1

    # Print with signal level indicator
    signal_indicator = "✓" if rms_level > 0.001 else "✗"
    print(f"{int(bass):4d},{int(mid):4d},{int(treble):4d},{beat} | RMS: {rms_level:.4f} {signal_indicator}")

def update_plot(frame):
    with data_lock:
        bass_data = list(bass_history)
        mid_data = list(mid_history)
        treble_data = list(treble_history)
        beats = list(beat_flags)
    
    ax.clear()
    
    if len(bass_data) > 0:
        x = np.arange(len(bass_data))
        ax.plot(x, bass_data, label='Bass', color='blue', linewidth=2)
        ax.plot(x, mid_data, label='Mid', color='green', linewidth=2)
        ax.plot(x, treble_data, label='Treble', color='red', linewidth=2)
        
    ax.set_ylabel('Amplitude')
    ax.set_xlabel('Time (samples)')
    ax.set_title('Real-time Audio Frequency Analysis')
    ax.legend(loc='upper right')
    ax.grid(True, alpha=0.3)
    
    # Set y-axis limits and draw beat markers
    if bass_data or mid_data or treble_data:
        max_val = max(
            max(bass_data) if bass_data else 0,
            max(mid_data) if mid_data else 0,
            max(treble_data) if treble_data else 0
        )
        y_max = max_val * 1.1
        ax.set_ylim(0, y_max)
        
        # Draw vertical lines for beats
        beat_positions = [i for i, is_beat in enumerate(beats) if is_beat]
        if beat_positions:
            ax.vlines(beat_positions, 0, y_max, colors='orange', linestyles='--', 
                     linewidth=2, alpha=0.7, label='Beat')
    else:
        ax.set_ylim(0, 100)

# Set up the plot
fig, ax = plt.subplots(figsize=(12, 6))
plt.ion()

# Start the animation
ani = animation.FuncAnimation(fig, update_plot, interval=50, blit=False, cache_frame_data=False)
plt.show(block=False)

# Find and use loopback device for system audio capture
def find_loopback_device():
    """Find a loopback device that captures system audio output."""
    devices = sd.query_devices()
    
    # Look for common loopback device names
    loopback_keywords = ['blackhole', 'soundflower', 'loopback', 'multi-output', 
                        'aggregate', 'virtual', 'system audio']
    
    for i, device in enumerate(devices):
        name_lower = device['name'].lower()
        # Check if it's an input device and matches loopback keywords
        if device['max_input_channels'] > 0:
            if any(keyword in name_lower for keyword in loopback_keywords):
                print(f"Found loopback device: {device['name']} (device {i})")
                print("\n⚠️  IMPORTANT: To capture system audio AND hear it on speakers:")
                print("   Create a Multi-Output Device:")
                print("   1. Open 'Audio MIDI Setup' (search in Spotlight)")
                print("   2. Click the '+' button at bottom left → 'Create Multi-Output Device'")
                print("   3. In the right panel, check BOTH:")
                print("      ✓ Your speakers/headphones (e.g., 'MacBook Pro Speakers')")
                print("      ✓ BlackHole 64ch")
                print("   4. In System Settings > Sound, set Output to this Multi-Output Device")
                print("   5. Play some audio - you should hear it AND see signal in this script")
                print("      (look for ✓ indicator and RMS > 0.001)\n")
                return i
    
    # If no loopback found, list available input devices
    print("\nNo loopback device found. Available input devices:")
    print("=" * 60)
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            print(f"  Device {i}: {device['name']}")
            print(f"    Channels: {device['max_input_channels']}, "
                  f"Sample Rate: {device['default_samplerate']}")
    print("\nTo capture system audio on macOS, you may need to install:")
    print("  - BlackHole: https://github.com/ExistentialAudio/BlackHole")
    print("  - Or use Soundflower (older, less maintained)")
    print("\nUsing default input device (microphone) for now...")
    return None

# Try to find loopback device, otherwise use default
input_device = find_loopback_device()

# Run stream
try:
    stream_kwargs = {
        'callback': analyze_audio,
        'channels': 1,
        'samplerate': 44100,
        'blocksize': 1024
    }
    if input_device is not None:
        stream_kwargs['device'] = input_device
        print(f"Capturing from system audio (device {input_device})")
    else:
        print("Capturing from microphone (default device)")
    
    with sd.InputStream(**stream_kwargs):
        while True:
            plt.pause(0.1)
            time.sleep(0.1)
except KeyboardInterrupt:
    print("\nStopping...")
    plt.close()
except Exception as e:
    print(f"\nError: {e}")
    print("\nIf you're trying to use a loopback device, make sure it's installed and selected.")
    plt.close()