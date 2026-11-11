import numpy as np
import wave

sr = 44100
dur = 7 * 60  # 7 minutes
t = np.linspace(0, dur, int(sr * dur), endpoint=False)

# D minor epic drone: D2 A2 D3 F3 A3
freqs = [73.42, 110.00, 146.83, 174.61, 220.00, 293.66, 349.23]

def swell(tg, period, max_amp):
    return max_amp * (0.5 - 0.5 * np.cos(2 * np.pi * tg / period))

mix = np.zeros_like(t)
# root drone (slow swells, same period, staggered)
for i, f in enumerate(freqs):
    amp = 0.10 + 0.02 * (i % 3)
    phase = np.random.uniform(0, 2 * np.pi)
    wave_ = np.sin(2 * np.pi * f * t + phase)
    env = swell(t + i * 20, 38 + i * 4, amp)
    mix += wave_ * env

# detune shimmer (octave + fifth, very quiet)
for f in [293.66, 440.00, 523.25]:
    mix += 0.012 * np.sin(2 * np.pi * f * t + np.pi / 7) * swell(t, 47, 1.0)

# sub root
mix += 0.10 * np.sin(2 * np.pi * 36.71 * t) * (0.65 + 0.35 * np.sin(2 * np.pi * t / 55))

# very soft noise wash (reverb feel)
rng = np.random.default_rng(7)
noise = rng.standard_normal(len(t))
# cheap lowpass
kernel_size = 2000
kernel = np.ones(kernel_size) / kernel_size
low = np.convolve(noise, kernel, mode='same')
mix += low * 0.008

# gentle master envelope: fade in/out 10s
fade = int(sr * 10)
env2 = np.ones(len(t))
env2[:fade] = np.linspace(0, 1, fade) ** 1.5
env2[-fade:] = np.linspace(1, 0, fade) ** 1.5
mix *= env2

# limiter-ish normalize and stereo
mix = np.tanh(mix * 1.4)
mix = mix / np.max(np.abs(mix)) * 0.82
stereo = np.vstack([mix, np.roll(mix, 2200) * 0.92])

with wave.open(r"C:\Users\Park-Edge\Documents\Default Project\youtube-automation\assets\music\epic_ambient.wav", "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(sr)
    w.writeframes((stereo.T * 32767).astype(np.int16).tobytes())
print("synth OK")
