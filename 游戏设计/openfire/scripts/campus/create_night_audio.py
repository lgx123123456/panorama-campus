"""Reproduce the original instrumental score and synthetic rain, using only NumPy.

Run from any directory with Python and NumPy. WAVs are 24 kHz stereo PCM16.
Every note/reverb tail wraps into the next loop. Rain uses periodic FFT noise.
These are original procedural compositions/synthesis, not field recordings.
"""

from pathlib import Path
import wave

import numpy as np


RATE = 24000
OUTPUT = Path(__file__).resolve().parents[2] / "assets" / "audio"


def frequency(midi: int) -> float:
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def add_wrapped(track: np.ndarray, sound: np.ndarray, start: float, pan: float) -> None:
    """Equal-power stereo placement with cyclic tails and arbitrary loop onset."""
    indices = (np.arange(len(sound)) + round(start * RATE)) % len(track)
    track[indices, 0] += sound * np.sqrt((1.0 - pan) * 0.5)
    track[indices, 1] += sound * np.sqrt((1.0 + pan) * 0.5)


def piano_note(midi: int, duration: float = 7.5) -> np.ndarray:
    time = np.arange(round(duration * RATE)) / RATE
    pitch = frequency(midi)
    sound = np.zeros_like(time)
    for harmonic, level in ((1, 1.0), (2, 0.25), (3, 0.12), (4, 0.045)):
        sound += level * np.sin(2 * np.pi * pitch * harmonic * time) * np.exp(
            -time * (0.65 + harmonic * 0.21)
        )
    # A restrained inharmonic upper partial gives the notes a soft bell colour.
    sound += 0.055 * np.sin(2 * np.pi * pitch * 2.756 * time) * np.exp(-time * 1.6)
    attack = 1.0 - np.exp(-time / 0.025)
    release = np.minimum((duration - time) / 0.7, 1.0)
    return sound * attack * np.maximum(release, 0.0)


def make_music() -> np.ndarray:
    duration = 64.0
    track = np.zeros((round(duration * RATE), 2))
    # Eight slow harmonic phrases in D minor, including a quiet dominant resolve.
    chords = ((38, 53, 57, 62), (34, 50, 53, 57), (31, 50, 55, 58),
              (33, 49, 52, 57), (38, 53, 57, 64), (34, 50, 53, 60),
              (31, 50, 55, 58), (33, 49, 52, 57))
    pad_time = np.arange(16 * RATE) / RATE
    pad_window = np.sin(np.pi * pad_time / 16.0) ** 2
    for phrase, chord in enumerate(chords):
        for voice, midi in enumerate(chord):
            pitch = frequency(midi)
            # Quantise to the complete loop period for exactly periodic phases.
            pitch = round(pitch * duration) / duration
            phase = (phrase * 8 - 4 + pad_time) * 2 * np.pi
            pad = np.sin(phase * pitch)
            pad += 0.18 * np.sin(phase * pitch * 2)
            pad += 0.12 * np.sin(phase * (pitch + 1.0 / duration))
            pad *= pad_window * (0.095 if voice == 0 else 0.038)
            add_wrapped(track, pad, phrase * 8 - 4, (voice - 1.5) * 0.34)
    # Original sparse call-and-answer melody. Silences leave room for footsteps.
    melody = ((1.0, 69), (4.5, 65), (9.0, 65), (12.0, 62),
              (17.0, 67), (21.0, 65), (25.0, 64), (28.5, 61),
              (33.0, 69), (36.0, 72), (41.5, 70), (45.0, 65),
              (49.0, 67), (52.5, 62), (57.0, 64), (60.0, 61))
    for index, (onset, midi) in enumerate(melody):
        note = piano_note(midi) * (0.17 if index % 2 == 0 else 0.13)
        pan = -0.28 if index % 2 == 0 else 0.28
        add_wrapped(track, note, onset, pan)
        for delay, gain in ((0.37, 0.17), (0.81, 0.09), (1.43, 0.045)):
            add_wrapped(track, note * gain, onset + delay, -pan)
    return track


def periodic_noise(rng: np.random.Generator, frames: int, low: float,
                   high: float, slope: float) -> np.ndarray:
    frequencies = np.fft.rfftfreq(frames, 1.0 / RATE)
    safe = np.maximum(frequencies, 1.0)
    shape = (safe / 1000.0) ** slope
    shape *= (1.0 - np.exp(-(safe / low) ** 2)) * np.exp(-(safe / high) ** 2)
    spectrum = rng.standard_normal(len(shape)) + 1j * rng.standard_normal(len(shape))
    spectrum *= shape
    spectrum[0] = 0.0
    spectrum[-1] = spectrum[-1].real
    sound = np.fft.irfft(spectrum, n=frames)
    return sound / np.sqrt(np.mean(sound * sound))


def make_rain() -> np.ndarray:
    rng = np.random.default_rng(20261116)
    duration = 24.0
    frames = round(duration * RATE)
    time = np.arange(frames) / RATE
    track = np.zeros((frames, 2))
    shared = periodic_noise(rng, frames, 70.0, 4200.0, -0.35)
    swell = 1.0 + 0.055 * np.sin(2 * np.pi * time / duration)
    swell += 0.025 * np.sin(2 * np.pi * time * 3 / duration + 0.7)
    for channel in range(2):
        diffuse = periodic_noise(rng, frames, 450.0, 6500.0, -0.1)
        low = periodic_noise(rng, frames, 45.0, 950.0, -0.45)
        track[:, channel] = (0.095 * shared + 0.065 * diffuse + 0.035 * low) * swell
    # A dense, low-level patter overlays the broad-band wash without loud drops.
    drop_time = np.arange(round(0.09 * RATE)) / RATE
    for _ in range(3600):
        pitch = rng.uniform(900.0, 4400.0)
        decay = rng.uniform(0.007, 0.022)
        sound = np.sin(2 * np.pi * pitch * drop_time) * np.exp(-drop_time / decay)
        sound *= (1 - np.exp(-drop_time / 0.0012))
        sound *= np.minimum((0.09 - drop_time) / 0.015, 1.0)
        add_wrapped(track, sound * rng.uniform(0.018, 0.047),
                    rng.uniform(0.0, duration), rng.uniform(-0.9, 0.9))
    return track


def save(name: str, track: np.ndarray, peak: float) -> None:
    track -= track.mean(axis=0)
    track *= peak / np.max(np.abs(track))
    pcm = np.rint(track * 32767.0).astype("<i2")
    path = OUTPUT / name
    with wave.open(str(path), "wb") as file:
        file.setnchannels(2)
        file.setsampwidth(2)
        file.setframerate(RATE)
        file.writeframes(pcm.tobytes())
    seam = float(np.max(np.abs(track[0] - track[-1])))
    step = float(np.sqrt(np.mean(np.diff(track, axis=0) ** 2)))
    print(f"{name}: {len(track) / RATE:.1f}s, stereo {RATE}Hz PCM16, "
          f"peak={np.max(np.abs(track)):.5f}, rms={np.sqrt(np.mean(track**2)):.5f}, "
          f"loop_seam={seam:.6f}, adjacent_step_rms={step:.6f}, "
          f"bytes={path.stat().st_size}")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    save("campus_night_music.wav", make_music(), 0.76)
    save("campus_rain.wav", make_rain(), 0.74)


if __name__ == "__main__":
    main()
