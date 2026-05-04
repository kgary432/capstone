import threading
import time
from collections import deque

import matplotlib.animation as animation
import matplotlib.pyplot as plt
import numpy as np
import serial
import sounddevice as sd

# To run: poetry run python main.py
# Cntrl+C to stop

# Shared data storage for thread-safe access
# Threading is due to performance issues and data access issues:
# - analyze_audio() runs in sounddevice's audio callback thread (called ~40 times/sec)
# - update_plot() runs in matplotlib's animation thread (called ~20 times/sec)
# Both threads access the same shared data (bass_history, etc.), so it needs a lock
# to prevent race conditions where one thread reads while the other writes
data_lock = threading.Lock()
bass_history = deque(maxlen=200)
mid_history = deque(maxlen=200)
treble_history = deque(maxlen=200)
beat_flags = deque(
    maxlen=200
)  # Track beats for visualization (0=no beat, 1=bass, 2=mid, 3=treble)
recent_bass = deque(maxlen=20)  # Keep last 20 bass values for beat detection
recent_mid = deque(maxlen=20)  # Keep last 20 mid values for beat detection
recent_treble = deque(maxlen=20)  # Keep last 20 treble values for beat detection
sample_counter = (
    0  # Continuously incrementing sample counter (not tied to deque length)
)
last_bass_sample = -1  # Track when last bass beat was detected (sample index)
last_mid_sample = -1  # Track when last mid beat was detected (sample index)
last_treble_sample = -1  # Track when last treble beat was detected (sample index)
first_sample_in_window = (
    0  # Track the sample counter value of the first item in the history deques
)

# tweakable parameters, play around with these until you get the desired effect
BEAT_COOLDOWN = (
    5  # Minimum samples between beats (prevents multiple detections per beat)
)
BEAT_THRESHOLD = 2  # Threshold for beat detection


# Arduino serial connection (initialized in main)
arduino = None


#
#
# Functions!
# all helper function logic defined below
# main is below this section
#
#

def calculate_audio_frequencies(samples, sample_rate=44100):
    """
    Calculate bass, mid, and treble frequency amplitudes from audio samples.
    
    Args:
        samples: Audio samples array
        sample_rate: Sample rate in Hz (default: 44100)
    
    Returns:
        Tuple of (bass, mid, treble) amplitude values
    """
    fft = np.abs(np.fft.rfft(samples))
    freqs = np.fft.rfftfreq(len(samples), 1 / sample_rate)
    
    bass = np.mean(fft[(freqs >= 20) & (freqs < 250)])
    mid = np.mean(fft[(freqs >= 250) & (freqs < 4000)])
    treble = np.mean(fft[(freqs >= 4000) & (freqs < 16000)])
    
    return bass, mid, treble


def calculate_rms_level(indata):
    """
    Calculate the RMS (Root Mean Square) level of audio input.
    
    Args:
        indata: Audio input data array
    
    Returns:
        RMS level as a float
    """
    return np.sqrt(np.mean(indata**2))


def reset_beat_sample_if_outdated(last_beat_sample, current_sample, cooldown):
    """
    Reset the last beat sample counter if it's too far behind.
    This prevents the beat detection from getting stuck when the window wraps around.
    
    Args:
        last_beat_sample: The sample index of the last detected beat
        current_sample: The current sample counter value
        cooldown: The beat cooldown period
    
    Returns:
        Updated last_beat_sample value
    """
    samples_since_last_beat = current_sample - last_beat_sample
    
    if last_beat_sample > 0 and samples_since_last_beat > 400:
        return current_sample - cooldown
    
    return last_beat_sample


def detect_beat_in_frequency(current_value, recent_values, last_beat_sample, 
                             current_sample, threshold, cooldown):
    """
    Detect if a beat occurred in a specific frequency range.
    
    Args:
        current_value: Current frequency amplitude value
        recent_values: Deque of recent frequency values
        last_beat_sample: Sample index of last detected beat for this frequency
        current_sample: Current sample counter value
        threshold: Multiplier threshold for beat detection (e.g., 2.0 means 2x average)
        cooldown: Minimum samples between beats
    
    Returns:
        Tuple of (beat_detected: bool, updated_last_beat_sample: int)
    """
    if len(recent_values) < 5:
        return False, last_beat_sample
    
    # Calculate average of recent values, excluding the current one
    recent_avg = np.mean(list(recent_values)[:-1])
    
    # Reset last beat sample if it's too far behind
    updated_last_beat = reset_beat_sample_if_outdated(
        last_beat_sample, current_sample, cooldown
    )
    samples_since_last_beat = current_sample - updated_last_beat
    
    # Check if current value exceeds threshold and cooldown has passed
    if (current_value > recent_avg * threshold and 
        samples_since_last_beat >= cooldown):
        return True, current_sample
    
    return False, updated_last_beat


def send_arduino_command(arduino_connection, led_value, beat_type_name):
    """
    Send a command to the Arduino to control LEDs.
    
    Args:
        arduino_connection: Serial connection to Arduino (or None)
        led_value: LED value to send (1=bass, 2=mid, 3=treble)
        beat_type_name: Name of the beat type for logging (e.g., "BASS", "MID")
    """
    if arduino_connection and arduino_connection.is_open:
        try:
            arduino_connection.reset_input_buffer()
            arduino_connection.write(f"{led_value}\n".encode("utf-8"))
            arduino_connection.flush()
            print(f"{beat_type_name} BEAT DETECTED. Sent LED value: {led_value}")
        except Exception as e:
            print(f"Error sending to Arduino: {e}")


def update_history_and_sample_tracking(bass, mid, treble, beat, sample_counter):
    """
    Update the history deques and track sample window boundaries.
    
    Args:
        bass: Current bass amplitude value
        mid: Current mid amplitude value
        treble: Current treble amplitude value
        beat: Beat type detected (0=none, 1=bass, 2=mid, 3=treble)
        sample_counter: Current sample counter value
    """
    global first_sample_in_window
    
    # Track when the history window wraps around
    was_full = len(bass_history) == bass_history.maxlen
    
    # Store values for visualization
    bass_history.append(bass)
    mid_history.append(mid)
    treble_history.append(treble)
    beat_flags.append(beat)
    
    # Update first_sample_in_window when deque wraps around
    if was_full:
        first_sample_in_window = sample_counter - 400
    elif sample_counter == 1:
        first_sample_in_window = 1


def analyze_audio(indata, frames, time_info, status):
    """
    Main audio analysis callback function. Called by sounddevice for each audio block.
    Performs frequency analysis, beat detection, and sends commands to Arduino.
    """
    global last_bass_sample, last_mid_sample, last_treble_sample, sample_counter
    
    # Calculate audio input level
    rms_level = calculate_rms_level(indata)
    
    # Extract audio samples and calculate frequency bands
    samples = indata[:, 0]
    bass, mid, treble = calculate_audio_frequencies(samples)
    
    # Beat detection: compare current values to recent averages
    with data_lock:
        # Add current values to recent history
        recent_bass.append(bass)
        recent_mid.append(mid)
        recent_treble.append(treble)
        sample_counter += 1
        
        # Detect beats in priority order: bass > mid > treble
        beat = 0  # 0=no beat, 1=bass, 2=mid, 3=treble
        
        # Check for bass beat
        bass_beat_detected, last_bass_sample = detect_beat_in_frequency(
            bass, recent_bass, last_bass_sample, sample_counter,
            BEAT_THRESHOLD, BEAT_COOLDOWN
        )
        if bass_beat_detected:
            beat = 1
            send_arduino_command(arduino, 1, "BASS")
        
        # Check for mid beat (only if bass beat not detected)
        if beat == 0:
            mid_beat_detected, last_mid_sample = detect_beat_in_frequency(
                mid, recent_mid, last_mid_sample, sample_counter,
                BEAT_THRESHOLD, BEAT_COOLDOWN
            )
            if mid_beat_detected:
                beat = 2
                send_arduino_command(arduino, 2, "MID")
        
        # Check for treble beat (only if no other beat detected)
        if beat == 0:
            treble_beat_detected, last_treble_sample = detect_beat_in_frequency(
                treble, recent_treble, last_treble_sample, sample_counter,
                BEAT_THRESHOLD, BEAT_COOLDOWN
            )
            if treble_beat_detected:
                beat = 3
                send_arduino_command(arduino, 3, "TREBLE")
        
        # Update history and tracking
        update_history_and_sample_tracking(bass, mid, treble, beat, sample_counter)
    
    # Print current status with signal level indicator
    signal_indicator = "✓" if rms_level > 0.001 else "✗"
    print(
        f"{int(bass):4d},{int(mid):4d},{int(treble):4d},{beat} | RMS: {rms_level:.4f} {signal_indicator}"
    )


def get_plot_data():
    """
    Safely retrieve plot data from shared data structures.
    
    Returns:
        Tuple of (bass_data, mid_data, treble_data, beats) as lists
    """
    with data_lock:
        bass_data = list(bass_history)
        mid_data = list(mid_history)
        treble_data = list(treble_history)
        beats = list(beat_flags)
    return bass_data, mid_data, treble_data, beats


def plot_frequency_lines(ax, bass_data, mid_data, treble_data):
    """
    Plot the frequency amplitude lines on the graph.
    
    Args:
        ax: Matplotlib axes object
        bass_data: List of bass amplitude values
        mid_data: List of mid amplitude values
        treble_data: List of treble amplitude values
    """
    if len(bass_data) > 0:
        x = np.arange(len(bass_data))
        ax.plot(x, bass_data, label="Bass", color="blue", linewidth=2)
        ax.plot(x, mid_data, label="Mid", color="green", linewidth=2)
        ax.plot(x, treble_data, label="Treble", color="red", linewidth=2)


def setup_plot_axes(ax):
    """
    Configure the plot axes labels, title, legend, and grid.
    
    Args:
        ax: Matplotlib axes object
    """
    ax.set_ylabel("Amplitude")
    ax.set_xlabel("Time (samples)")
    ax.set_title("Real-time Audio Frequency Analysis")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)


def calculate_y_axis_limit(bass_data, mid_data, treble_data):
    """
    Calculate the maximum y-axis limit based on the data.
    
    Args:
        bass_data: List of bass amplitude values
        mid_data: List of mid amplitude values
        treble_data: List of treble amplitude values
    
    Returns:
        Maximum y-axis value (with 10% padding)
    """
    max_val = max(
        max(bass_data) if bass_data else 0,
        max(mid_data) if mid_data else 0,
        max(treble_data) if treble_data else 0,
    )
    return max_val * 1.1


def find_beat_positions(beats, beat_type):
    """
    Find the positions (indices) where beats of a specific type occurred.
    
    Args:
        beats: List of beat flags (0=none, 1=bass, 2=mid, 3=treble)
        beat_type: Type of beat to find (1=bass, 2=mid, 3=treble)
    
    Returns:
        List of indices where beats of the specified type occurred
    """
    return [i for i, beat_flag in enumerate(beats) if beat_flag == beat_type]


def draw_beat_markers(ax, beats, y_max):
    """
    Draw vertical lines on the plot to mark where beats were detected.
    
    Args:
        ax: Matplotlib axes object
        beats: List of beat flags (0=none, 1=bass, 2=mid, 3=treble)
        y_max: Maximum y-axis value for drawing vertical lines
    """
    # Find positions for each beat type
    bass_beat_positions = find_beat_positions(beats, 1)
    mid_beat_positions = find_beat_positions(beats, 2)
    treble_beat_positions = find_beat_positions(beats, 3)
    
    # Draw vertical lines for each beat type
    if bass_beat_positions:
        ax.vlines(
            bass_beat_positions,
            0,
            y_max,
            colors="blue",
            linestyles="--",
            linewidth=2,
            alpha=0.7,
            label="Bass Beat",
        )
    if mid_beat_positions:
        ax.vlines(
            mid_beat_positions,
            0,
            y_max,
            colors="green",
            linestyles="--",
            linewidth=2,
            alpha=0.7,
            label="Mid Beat",
        )
    if treble_beat_positions:
        ax.vlines(
            treble_beat_positions,
            0,
            y_max,
            colors="red",
            linestyles="--",
            linewidth=2,
            alpha=0.7,
            label="Treble Beat",
        )


def update_plot(frame):
    """
    Update the plot with the latest audio frequency data and beat markers.
    Called by matplotlib animation for each frame.
    """
    # Get current data from shared structures
    bass_data, mid_data, treble_data, beats = get_plot_data()
    
    # Clear the plot and redraw everything
    ax.clear()
    
    # Plot frequency lines if we have data
    plot_frequency_lines(ax, bass_data, mid_data, treble_data)
    
    # Set up axes labels and formatting
    setup_plot_axes(ax)
    
    # Set y-axis limits and draw beat markers
    if bass_data or mid_data or treble_data:
        y_max = calculate_y_axis_limit(bass_data, mid_data, treble_data)
        ax.set_ylim(0, y_max)
        draw_beat_markers(ax, beats, y_max)
    else:
        # Default y-axis limit when no data is available
        ax.set_ylim(0, 100)


def initialize_arduino_connection(port="/dev/cu.usbmodem1101", baud_rate=9600):
    """
    Initialize connection to Arduino for LED control.
    
    Args:
        port: Serial port path (default: "/dev/cu.usbmodem1101")
        baud_rate: Serial communication baud rate (default: 9600)
    
    Returns:
        Serial connection object, or None if connection failed
    """
    try:
        arduino_conn = serial.Serial(port, baud_rate, timeout=1)
        time.sleep(2)  # Give Arduino time to reset
        print("Arduino connected successfully!")
        
        # Discard any initial messages from Arduino
        time.sleep(0.5)
        arduino_conn.reset_input_buffer()
        return arduino_conn
    except serial.SerialException as e:
        print(f"Serial connection error: {e}")
        print("Continuing without Arduino - beat detection will still work but LEDs won't update.")
        print("Make sure the Arduino is connected and the port is correct.")
        return None
    except Exception as e:
        print(f"Unexpected error connecting to Arduino: {e}")
        print("Continuing without Arduino - beat detection will still work but LEDs won't update.")
        return None


def setup_plot():
    """
    Set up the matplotlib plot and animation.
    
    Returns:
        Tuple of (figure, axes, animation) objects
    """
    fig, ax = plt.subplots(figsize=(12, 6))
    plt.ion()
    
    # Start the animation
    ani = animation.FuncAnimation(
        fig, update_plot, interval=50, blit=False, cache_frame_data=False
    )
    plt.show(block=False)
    
    return fig, ax, ani


def find_loopback_device():
    """
    Find a loopback device that captures system audio output.
    
    Returns:
        Device index if found, or None if no loopback device is available

        NOTE::::::
        Most of this is broken and doesn't run but it breaks way worse if deleted. it's become structural, 
        change at your own risk!
    """
    devices = sd.query_devices()
    
    # Look for common loopback device names
    loopback_keywords = [
        "blackhole",
        "soundflower",
        "loopback",
        "multi-output",
        "aggregate",
        "virtual",
        "system audio",
    ]
    
    for i, device in enumerate(devices):
        name_lower = device["name"].lower()
        # Check if it's an input device and matches loopback keywords
        if device["max_input_channels"] > 0:
            if any(keyword in name_lower for keyword in loopback_keywords):
                print(f"Found loopback device: {device['name']} (device {i})")
                print("\n IMPORTANT: To capture system audio AND hear it on speakers:")
                print("   Create a Multi-Output Device:")
                print("   1. Open 'Audio MIDI Setup' (search in Spotlight)")
                print(
                    "   2. Click the '+' button at bottom left → 'Create Multi-Output Device'"
                )
                print("   3. In the right panel, check BOTH:")
                print("      ✓ Your speakers/headphones (e.g., 'MacBook Pro Speakers')")
                print("      ✓ BlackHole 64ch")
                print(
                    "   4. In System Settings > Sound, set Output to this Multi-Output Device"
                )
                print(
                    "   5. Play some audio - you should hear it AND see signal in this script"
                )
                print("      (look for ✓ indicator and RMS > 0.001)\n")
                return i
    
    # If no loopback found, list available input devices
    print("\nNo loopback device found. Available input devices:")
    print("=" * 60)
    for i, device in enumerate(devices):
        if device["max_input_channels"] > 0:
            print(f"  Device {i}: {device['name']}")
            print(
                f"    Channels: {device['max_input_channels']}, "
                f"Sample Rate: {device['default_samplerate']}"
            )
    print("\nTo capture system audio on macOS, you may need to install:")
    print("  - BlackHole: https://github.com/ExistentialAudio/BlackHole")
    print("  - Or use Soundflower (older, less maintained)")
    print("\nUsing default input device (microphone) for now...")
    return None


def create_audio_stream_config(input_device=None):
    """
    Create configuration dictionary for the audio input stream.
    
    Args:
        input_device: Device index for audio input, or None for default
    
    Returns:
        Dictionary of stream configuration parameters
    """
    stream_kwargs = {
        "callback": analyze_audio,
        "channels": 1,
        "samplerate": 44100,
        "blocksize": 1024,
    }
    
    if input_device is not None:
        stream_kwargs["device"] = input_device
        print(f"Capturing from system audio (device {input_device})")
    else:
        print("Capturing from microphone (default device)")
    
    return stream_kwargs


def print_startup_info():
    """Print information about beat detection and LED commands."""
    print("\nBeat detection active. LED commands:")
    print("   - Bass beats → LED value 1")
    print("   - Mid beats → LED value 2")
    print("   - Treble beats → LED value 3")
    print("Press Ctrl+C to stop.\n")


def cleanup_resources(arduino_connection, figure):
    """
    Clean up resources when shutting down.
    
    Args:
        arduino_connection: Serial connection to close (if open)
        figure: Matplotlib figure to close
    """
    if arduino_connection and arduino_connection.is_open:
        arduino_connection.close()
    plt.close(figure)


def run_audio_analysis_loop():
    """
    Main loop that runs the audio analysis stream and plot updates.
    Handles keyboard interrupts and errors gracefully.
    """
    # Try to find loopback device, otherwise use default
    input_device = find_loopback_device()
    
    # Create audio stream configuration
    stream_kwargs = create_audio_stream_config(input_device)
    
    # Print startup information
    print_startup_info()
    
    # Run audio stream
    try:
        with sd.InputStream(**stream_kwargs):
            while True:
                plt.pause(0.1)
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping...")
        cleanup_resources(arduino, fig)
    except Exception as e:
        print(f"\nError: {e}")
        print("\nIf you're trying to use a loopback device, make sure it's installed and selected.")
        cleanup_resources(arduino, fig)



# Main execution
if __name__ == "__main__":
    # Initialize Arduino connection
    # EDIT arduino path HERE!!!!
    # Top port: /dev/cu.usbmodem101
    # Bottom port: /dev/cu.usbmodem1101
    arduino = initialize_arduino_connection("/dev/cu.usbmodem1101")
    
    # Set up the plot
    fig, ax, ani = setup_plot()
    
    # Run the main audio analysis loop
    run_audio_analysis_loop()
