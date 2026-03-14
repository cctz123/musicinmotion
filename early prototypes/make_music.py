import numpy as np
import sounddevice as sd

def generate_do():
    duration = 2
    frequency = 261.63
    sample_rate = 44100
    t = np.linspace(0, duration, int(sample_rate*duration), endpoint = False)
    audio_signal = (
        0.5 * np.sin(2 * np.pi * frequency * t) +
        0.4 * np.sin(2 * np.pi * frequency * 2 * t) +
        0.3 * np.sin(2 * np.pi * frequency * 3 * t) +
        0.2 * np.sin(2 * np.pi * frequency * 4 * t) +
        0.1 * np.sin(2 * np.pi * frequency * 5 * t) +
        0.05 * np.sin(2 * np.pi * frequency * 6 * t) +
        0.03 * np.sin(2 * np.pi * frequency * 7 * t) +
        0.02 * np.sin(2 * np.pi * frequency * 8 * t)

    )
    return audio_signal

def generate_re():
    duration = 2
    frequency = 293.66
    sample_rate = 44100
    t = np.linspace(0, duration, int(sample_rate*duration), endpoint = False)
    audio_signal = (
        0.5 * np.sin(2 * np.pi * frequency * t) +
        0.4 * np.sin(2 * np.pi * frequency * 2 * t) +
        0.3 * np.sin(2 * np.pi * frequency * 3 * t) +
        0.2 * np.sin(2 * np.pi * frequency * 4 * t) +
        0.1 * np.sin(2 * np.pi * frequency * 5 * t) +
        0.05 * np.sin(2 * np.pi * frequency * 6 * t) +
        0.03 * np.sin(2 * np.pi * frequency * 7 * t) +
        0.02 * np.sin(2 * np.pi * frequency * 8 * t)

    )
    return audio_signal

def generate_mi():
    duration = 2
    frequency = 329.63
    sample_rate = 44100
    t = np.linspace(0, duration, int(sample_rate*duration), endpoint = False)
    audio_signal = (
        0.5 * np.sin(2 * np.pi * frequency * t) +
        0.4 * np.sin(2 * np.pi * frequency * 2 * t) +
        0.3 * np.sin(2 * np.pi * frequency * 3 * t) +
        0.2 * np.sin(2 * np.pi * frequency * 4 * t) +
        0.1 * np.sin(2 * np.pi * frequency * 5 * t) +
        0.05 * np.sin(2 * np.pi * frequency * 6 * t) +
        0.03 * np.sin(2 * np.pi * frequency * 7 * t) +
        0.02 * np.sin(2 * np.pi * frequency * 8 * t)

    )
    return audio_signal

def generate_fa():
    duration = 2
    frequency = 349.23
    sample_rate = 44100
    t = np.linspace(0, duration, int(sample_rate*duration), endpoint = False)
    audio_signal = (
        0.5 * np.sin(2 * np.pi * frequency * t) +
        0.4 * np.sin(2 * np.pi * frequency * 2 * t) +
        0.3 * np.sin(2 * np.pi * frequency * 3 * t) +
        0.2 * np.sin(2 * np.pi * frequency * 4 * t) +
        0.1 * np.sin(2 * np.pi * frequency * 5 * t) +
        0.05 * np.sin(2 * np.pi * frequency * 6 * t) +
        0.03 * np.sin(2 * np.pi * frequency * 7 * t) +
        0.02 * np.sin(2 * np.pi * frequency * 8 * t)

    )
    return audio_signal

def generate_so():
    duration = 2
    frequency = 392.00
    sample_rate = 44100
    t = np.linspace(0, duration, int(sample_rate*duration), endpoint = False)
    audio_signal = (
        0.5 * np.sin(2 * np.pi * frequency * t) +
        0.4 * np.sin(2 * np.pi * frequency * 2 * t) +
        0.3 * np.sin(2 * np.pi * frequency * 3 * t) +
        0.2 * np.sin(2 * np.pi * frequency * 4 * t) +
        0.1 * np.sin(2 * np.pi * frequency * 5 * t) +
        0.05 * np.sin(2 * np.pi * frequency * 6 * t) +
        0.03 * np.sin(2 * np.pi * frequency * 7 * t) +
        0.02 * np.sin(2 * np.pi * frequency * 8 * t)

    )
    return audio_signal

def generate_la():
    duration = 2
    frequency = 440.00
    sample_rate = 44100
    t = np.linspace(0, duration, int(sample_rate*duration), endpoint = False)
    audio_signal = (
        0.5 * np.sin(2 * np.pi * frequency * t) +
        0.4 * np.sin(2 * np.pi * frequency * 2 * t) +
        0.3 * np.sin(2 * np.pi * frequency * 3 * t) +
        0.2 * np.sin(2 * np.pi * frequency * 4 * t) +
        0.1 * np.sin(2 * np.pi * frequency * 5 * t) +
        0.05 * np.sin(2 * np.pi * frequency * 6 * t) +
        0.03 * np.sin(2 * np.pi * frequency * 7 * t) +
        0.02 * np.sin(2 * np.pi * frequency * 8 * t)

    )
    return audio_signal

def generate_ti():
    duration = 2
    frequency = 493.88
    sample_rate = 44100
    t = np.linspace(0, duration, int(sample_rate*duration), endpoint = False)
    audio_signal = (
        0.5 * np.sin(2 * np.pi * frequency * t) +
        0.4 * np.sin(2 * np.pi * frequency * 2 * t) +
        0.3 * np.sin(2 * np.pi * frequency * 3 * t) +
        0.2 * np.sin(2 * np.pi * frequency * 4 * t) +
        0.1 * np.sin(2 * np.pi * frequency * 5 * t) +
        0.05 * np.sin(2 * np.pi * frequency * 6 * t) +
        0.03 * np.sin(2 * np.pi * frequency * 7 * t) +
        0.02 * np.sin(2 * np.pi * frequency * 8 * t)

    )
    return audio_signal


def play_audio(audio_signal):
    sd.play(audio_signal, samplerate=44100)
    sd.wait()

do_audio = generate_do()
re_audio=generate_re()
mi_audio = generate_mi()
fa_audio = generate_fa()
so_audio = generate_so()
la_audio = generate_la()
ti_audio = generate_ti()
play_audio(do_audio)
play_audio(re_audio)
play_audio(mi_audio)
play_audio(fa_audio)
play_audio(so_audio)
play_audio(la_audio)
play_audio(ti_audio)


