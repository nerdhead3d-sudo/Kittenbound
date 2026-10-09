"""Genera la musica di sottofondo per sintesi (solo libreria standard), come gli effetti.

Uso (dalla root del progetto):
    python tools/generate_music.py            # tutti i brani
    python tools/generate_music.py boss       # solo quelli che iniziano così

Output: assets/music/<nome>.wav (mono, 16 bit, 22050 Hz), in loop senza stacchi: la coda che
supera la fine del giro viene sommata all'inizio. Per usare brani veri basta mettere al loro
posto un <nome>.ogg (ha la precedenza sul .wav).
"""
import math
import random
import sys
import wave
from array import array
from pathlib import Path

SR      = 22050
TAU     = 2 * math.pi
OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "music"

A4 = 440.0
_NAMES = {"C": -9, "C#": -8, "Db": -8, "D": -7, "D#": -6, "Eb": -6, "E": -5, "F": -4, "F#": -3,
          "Gb": -3, "G": -2, "G#": -1, "Ab": -1, "A": 0, "A#": 1, "Bb": 1, "B": 2}


def hz(name: str) -> float:
    """"A4" → 440, "D2" → 73.4 ..."""
    note, octave = name[:-1], int(name[-1])
    return A4 * 2 ** ((_NAMES[note] + 12 * (octave - 4)) / 12)


# ── Primitive ─────────────────────────────────────────────────────────────────

def buf(seconds: float):
    return [0.0] * int(SR * seconds)


def add(dst, src, at: float, gain: float = 1.0):
    """Somma src in dst a partire da `at` secondi; quello che supera la fine rientra
    dall'inizio, così il brano gira in loop senza stacchi."""
    i0, n = int(at * SR), len(dst)
    for i, v in enumerate(src):
        dst[(i0 + i) % n] += v * gain


def lowpass(x, fc):
    a = 1 - math.exp(-TAU * fc / SR)
    y, out = 0.0, []
    ap = out.append
    for v in x:
        y += a * (v - y)
        ap(y)
    return out


def lowpass_lfo(x, f_lo, f_hi, period):
    """Passa-basso con taglio che oscilla lento (respiro del suono)."""
    y, out = 0.0, []
    for i, v in enumerate(x):
        fc = f_lo + (f_hi - f_lo) * (0.5 - 0.5 * math.cos(TAU * i / (period * SR)))
        y += (1 - math.exp(-TAU * fc / SR)) * (v - y)
        out.append(y)
    return out


def highpass(x, fc):
    lp = lowpass(x, fc)
    return [a - b for a, b in zip(x, lp)]


def saw(freq, seconds, detune=0.0):
    f = freq * (1 + detune)
    step, ph, out = f / SR, random.random(), []
    for _ in range(int(seconds * SR)):
        ph += step
        if ph >= 1:
            ph -= 1
        out.append(2 * ph - 1)
    return out


def sine(freq, seconds, f_end=None):
    n = int(seconds * SR)
    out, ph = [], 0.0
    for i in range(n):
        f = freq if f_end is None else freq + (f_end - freq) * i / n
        ph += f / SR
        out.append(math.sin(TAU * ph))
    return out


def noise(seconds, seed):
    rng = random.Random(seed)
    return [rng.uniform(-1, 1) for _ in range(int(seconds * SR))]


def adsr(x, a, r, sustain_to=1.0):
    """Attacco lineare a secondi, poi rilascio esponenziale r (costante di tempo)."""
    na = max(1, int(a * SR))
    out = []
    for i, v in enumerate(x):
        if i < na:
            g = i / na
        else:
            g = sustain_to + (1 - sustain_to) * math.exp(-(i - na) / (r * SR))
        out.append(v * g)
    return out


def fade_edges(x, fin, fout):
    n, ni, no = len(x), max(1, int(fin * SR)), max(1, int(fout * SR))
    return [v * min(1.0, i / ni, (n - i) / no) for i, v in enumerate(x)]


def pluck(freq, seconds, bright=0.5, seed=0):
    """Corda pizzicata (Karplus-Strong)."""
    rng = random.Random(seed)
    period = max(2, int(SR / freq))
    line = [rng.uniform(-1, 1) for _ in range(period)]
    out, idx = [], 0
    for _ in range(int(seconds * SR)):
        nxt = (idx + 1) % period
        v = line[idx]
        line[idx] = 0.996 * 0.5 * (v + line[nxt])
        out.append(v)
        idx = nxt
    return lowpass(out, 1800 + 3000 * bright)


def bell(freq, seconds, seed=0):
    parts = [(1.0, 1.0, 1.0), (2.76, 0.45, 0.55), (5.4, 0.2, 0.3), (2.0, 0.25, 0.7)]
    n = int(seconds * SR)
    out = [0.0] * n
    for ratio, amp, dec in parts:
        f = freq * ratio
        k = TAU * f / SR
        tau = seconds * dec * 0.45 * SR
        for i in range(n):
            out[i] += amp * math.sin(k * i) * math.exp(-i / tau)
    return out


def echo(x, delay, feedback, wet):
    d = int(delay * SR)
    out = list(x)
    for i in range(d, len(out)):
        out[i] += out[i - d] * feedback
    return [a * (1 - wet) + b * wet for a, b in zip(x, out)]


def seamless_echo(x, delay, feedback, wet):
    """Eco che continua anche oltre il giro (i ritorni rientrano dall'inizio)."""
    n = len(x)
    d = int(delay * SR)
    out = list(x)
    for _ in range(2):                         # due passate: anche le code dell'inizio
        for i in range(n):
            out[i] = x[i] + out[(i - d) % n] * feedback
    return [a * (1 - wet) + b * wet for a, b in zip(x, out)]


def loop_fold(x, n, m):
    """x lungo n + m campioni → n campioni in loop: gli ultimi m sfumano dentro i primi m,
    così l'ultimo campione è seguito da quello che verrebbe davvero dopo (niente clic)."""
    out = x[:n]
    for i in range(m):
        w = i / m
        out[i] = x[i] * w + x[n + i] * (1 - w)
    return out


def drive(x, k):
    t = math.tanh(k)
    return [math.tanh(v * k) / t for v in x]


def normalize(x, peak=0.8):
    m = max(1e-9, max(abs(v) for v in x))
    return [v * peak / m for v in x]


def write(name, x):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = array("h", (int(max(-1.0, min(1.0, v)) * 32767) for v in x))
    with wave.open(str(OUT_DIR / f"{name}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


# ── Brani ─────────────────────────────────────────────────────────────────────

def hub():
    """Hub: tranquillo e caldo. Accordi morbidi, arpeggio pizzicato con eco, basso tondo."""
    random.seed(1)
    bpm  = 72
    beat = 60 / bpm
    bar  = 4 * beat
    prog = [("A", ["A3", "C4", "E4"]), ("F", ["F3", "A3", "C4"]), ("C", ["C4", "E4", "G4"]), ("G", ["G3", "B3", "D4"]),
            ("A", ["A3", "C4", "E4"]), ("F", ["F3", "A3", "C4"]), ("D", ["D4", "F4", "A4"]), ("E", ["E3", "G#3", "B3"])]
    total = len(prog) * 2 * bar
    pad_bus, arp_bus, bass_bus = buf(total), buf(total), buf(total)
    for k, (root, notes) in enumerate(prog):
        t0  = k * 2 * bar
        dur = 2 * bar + 1.2
        for nm in notes:                                          # pad: due seghe stonate di poco
            f = hz(nm)
            v = [a + b for a, b in zip(saw(f, dur, -0.004), saw(f, dur, 0.005))]
            add(pad_bus, fade_edges(lowpass(lowpass(v, 900), 1400), 1.0, 1.2), t0, 0.16)
        f_root = hz(root + "2")                                   # basso: radice a ogni battuta
        for b in range(2):
            add(bass_bus, adsr(sine(f_root, bar), 0.02, 0.9, 0.0), t0 + b * bar, 0.5)
        arp = [notes[0], notes[1], notes[2], notes[1]]            # arpeggio a ottavi, un'ottava sopra
        for i in range(16):
            nm = arp[i % 4]
            f = hz(nm) * 2
            vel = 0.75 if i % 4 == 0 else 0.5
            add(arp_bus, pluck(f, 1.2, 0.35, seed=k * 31 + i), t0 + i * beat / 2, 0.22 * vel)
    arp_bus = seamless_echo(arp_bus, beat * 0.75, 0.35, 0.35)
    out = [a + b + c for a, b, c in zip(pad_bus, arp_bus, bass_bus)]
    return normalize(lowpass(out, 6000), 0.75)


def dungeon():
    """Dungeon: buio e teso. Bordone che respira, vento, campane lontane e qualche tonfo."""
    random.seed(2)
    total = 48.0
    n, m  = int(total * SR), int(1.5 * SR)                  # strati continui: 1.5 s in più, poi piegati
    long_ = total + 1.5
    d1 = [a + b for a, b in zip(saw(hz("D2"), long_, -0.003), saw(hz("D2"), long_, 0.004))]
    d2 = saw(hz("A2"), long_, 0.002)
    drone = loop_fold(lowpass_lfo([a + 0.6 * b for a, b in zip(d1, d2)], 140, 520, 16.0), n, m)
    sub   = loop_fold(sine(hz("D1"), long_), n, m)
    wind  = lowpass_lfo(highpass(noise(long_, 7), 300), 400, 1600, 12.0)
    swell = [0.55 + 0.45 * math.sin(TAU * i / (24.0 * SR)) for i in range(len(wind))]
    wind  = loop_fold([w * g for w, g in zip(wind, swell)], n, m)
    bells = buf(total)
    scale = ["D4", "F4", "G4", "A4", "C5", "D5", "F5"]
    rng = random.Random(5)
    t = 1.5
    while t < total - 1:
        nm = rng.choice(scale)
        add(bells, bell(hz(nm), 3.5, seed=int(t * 10)), t, rng.uniform(0.12, 0.2))
        t += rng.choice([2.5, 3.0, 4.0, 4.5, 6.0])
    bells = seamless_echo(bells, 0.55, 0.45, 0.45)
    thuds = buf(total)
    for t in (6.0, 22.0, 38.0):
        add(thuds, adsr(sine(70, 1.2, 38), 0.005, 0.35, 0.0), t, 0.6)
    out = [0.30 * a + 0.35 * b + 0.18 * c + d + e for a, b, c, d, e in zip(drone, sub, wind, bells, thuds)]
    return normalize(out, 0.7)


def boss():
    """Boss: incalzante. Tamburi, basso ostinato frigio, colpi di ottoni ogni due battute."""
    random.seed(3)
    bpm  = 124
    beat = 60 / bpm
    bar  = 4 * beat
    bars = 16
    total = bars * bar
    drums, bass, stabs, hats = buf(total), buf(total), buf(total), buf(total)
    kick = adsr(sine(110, 0.35, 42), 0.002, 0.09, 0.0)
    tom  = adsr(sine(150, 0.3, 90), 0.002, 0.1, 0.0)
    snare_n = adsr(highpass(noise(0.25, 11), 1200), 0.001, 0.06, 0.0)
    snare = [a + 0.4 * b for a, b in zip(snare_n, adsr(sine(190, 0.25, 160), 0.001, 0.05, 0.0))]
    hat = adsr(highpass(noise(0.06, 12), 6000), 0.001, 0.012, 0.0)
    riff = ["D2", "D2", "Eb2", "D2", "D2", "F2", "Eb2", "C2"]
    for b in range(bars):
        t0 = b * bar
        for step in (0, 2.5, 3):                                 # cassa
            add(drums, kick, t0 + step * beat, 0.9)
        for step in (1, 3):                                       # rullante
            add(drums, snare, t0 + step * beat, 0.45)
        if b % 4 == 3:                                            # rullata di tom a fine frase
            for i, step in enumerate((3.0, 3.25, 3.5, 3.75)):
                add(drums, tom, t0 + step * beat, 0.5 + 0.1 * i)
        for i in range(8):
            add(hats, hat, t0 + i * beat / 2, 0.35 if i % 2 else 0.2)
        shift = 0 if b % 8 < 4 else 2                             # seconda metà: un tono su
        for i, nm in enumerate(riff):
            f = hz(nm) * 2 ** (shift / 12)
            note = adsr(lowpass(saw(f, beat / 2 * 0.95, 0.002), 700), 0.004, 0.12, 0.35)
            add(bass, note, t0 + i * beat / 2, 0.55)
        if b % 2 == 0:                                            # ottoni: accordo teso
            chord = ["D4", "A4", "D5"] if b % 8 < 4 else ["E4", "B4", "E5"]
            for nm in chord:
                v = [x + y for x, y in zip(saw(hz(nm), bar * 0.9, -0.004), saw(hz(nm), bar * 0.9, 0.004))]
                add(stabs, adsr(lowpass(v, 1600), 0.02, 0.25, 0.25), t0, 0.12)
    bass = drive(bass, 1.6)
    stabs = seamless_echo(stabs, beat * 0.75, 0.3, 0.3)
    out = [a + b + c + d for a, b, c, d in zip(drums, bass, stabs, hats)]
    return normalize(drive(out, 1.2), 0.75)


TRACKS = {"hub": hub, "dungeon": dungeon, "boss": boss}

if __name__ == "__main__":
    only = sys.argv[1:]
    for name, fn in TRACKS.items():
        if only and not any(name.startswith(o) for o in only):
            continue
        x = fn()
        write(name, x)
        print(f"{name:10s} {len(x) / SR:5.1f}s")
