"""Genera gli effetti sonori del gioco per sintesi procedurale (solo libreria standard).

Uso (dalla root del progetto):
    python tools/generate_sounds.py

Output: assets/sounds/<nome>.wav (mono, 16 bit). I suoni con più varianti si chiamano
<nome>_1.wav, <nome>_2.wav, ...: il gioco ne sceglie una a caso per evitare ripetizioni.
Per modificare un suono basta cambiare la sua funzione qui sotto e rilanciare lo script.
"""
import math
import random
import wave
from array import array
from pathlib import Path

SR      = 22050
OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "sounds"
TAU     = 2 * math.pi


# ── Primitive di sintesi ──────────────────────────────────────────────────────

def n(dur: float) -> int:
    return max(1, int(SR * dur))


def tone(freq, dur, shape="sine", freq_end=None, curve=1.0, vibrato=(0.0, 0.0)):
    """Oscillatore con glissando opzionale (freq → freq_end) e vibrato (Hz, profondità)."""
    out, ph, N = [], 0.0, n(dur)
    for i in range(N):
        u = i / max(1, N - 1)
        f = freq if freq_end is None else freq + (freq_end - freq) * (u ** curve)
        if vibrato[0]:
            f *= 1 + vibrato[1] * math.sin(TAU * vibrato[0] * i / SR)
        ph = (ph + f / SR) % 1.0
        if shape == "sine":
            v = math.sin(TAU * ph)
        elif shape == "square":
            v = 1.0 if ph < 0.5 else -1.0
        elif shape == "saw":
            v = 2 * ph - 1
        else:                                   # tri
            v = 4 * abs(ph - 0.5) - 1
        out.append(v)
    return out


def noise(dur, seed=0):
    rng = random.Random(seed)
    return [rng.uniform(-1, 1) for _ in range(n(dur))]


def lowpass(x, cutoff, cutoff_end=None):
    """Filtro passa-basso a un polo, con taglio che può scorrere nel tempo."""
    out, y, N = [], 0.0, len(x)
    for i, v in enumerate(x):
        fc = cutoff if cutoff_end is None else cutoff + (cutoff_end - cutoff) * i / max(1, N - 1)
        a = 1 - math.exp(-TAU * fc / SR)
        y += a * (v - y)
        out.append(y)
    return out


def highpass(x, cutoff):
    return [v - l for v, l in zip(x, lowpass(x, cutoff))]


def bandpass(x, lo, hi, hi_end=None):
    return lowpass(highpass(x, lo), hi, hi_end)


def env(x, attack=0.005, decay=0.2, hold=0.0):
    """Attacco lineare, tenuta, poi decadimento esponenziale (decay = costante di tempo)."""
    out = []
    for i, v in enumerate(x):
        t = i / SR
        if t < attack:
            a = t / attack
        elif t < attack + hold:
            a = 1.0
        else:
            a = math.exp(-(t - attack - hold) / decay)
        out.append(v * a)
    return out


def swell(x, peak_at=0.5):
    """Inviluppo a campana: cresce fino a peak_at (frazione) e poi si spegne."""
    N = len(x)
    out = []
    for i, v in enumerate(x):
        u = i / max(1, N - 1)
        a = (u / peak_at) if u < peak_at else (1 - u) / (1 - peak_at)
        out.append(v * a * a * (3 - 2 * a))
    return out


def tremolo(x, rate, depth):
    return [v * (1 - depth + depth * (0.5 + 0.5 * math.sin(TAU * rate * i / SR))) for i, v in enumerate(x)]


def gain(x, g):
    return [v * g for v in x]


def drive(x, k):
    """Saturazione morbida (tanh): rende ruggiti e colpi più ruvidi."""
    norm = math.tanh(k)
    return [math.tanh(v * k) / norm for v in x]


def mix(*parts):
    """parts = (segnale, inizio_in_secondi, guadagno) → somma."""
    length = max(int(at * SR) + len(sig) for sig, at, _ in parts)
    out = [0.0] * length
    for sig, at, g in parts:
        o = int(at * SR)
        for i, v in enumerate(sig):
            out[o + i] += v * g
    return out


def bell(freq, dur, ratios=(1, 2.76, 5.4), decays=(1.0, 0.5, 0.25), seed=0):
    """Campanella/metallo: parziali inarmoniche che si spengono a velocità diverse."""
    parts = []
    for r, d in zip(ratios, decays):
        parts.append((env(tone(freq * r, dur), 0.002, dur * d * 0.4), 0, 1 / len(ratios)))
    return mix(*parts)


def note(freq, dur, shape="tri", decay=None):
    return env(tone(freq, dur, shape), 0.004, decay or dur * 0.6)


def save(name, x, peak=0.85):
    m = max(1e-6, max(abs(v) for v in x))
    fade_in, fade_out = n(0.003), n(0.025)        # niente click all'inizio e alla fine
    data = array("h")
    for i, v in enumerate(x):
        a = min(1.0, i / fade_in, (len(x) - 1 - i) / fade_out)
        data.append(int(max(-1, min(1, v / m * peak * a)) * 32767))
    with wave.open(str(OUT_DIR / f"{name}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


NOTE = {"C5": 523.25, "E5": 659.25, "G5": 783.99, "A5": 880.0, "B5": 987.77,
        "C6": 1046.5, "E6": 1318.5, "G6": 1568.0, "C4": 261.63, "G4": 392.0}


# ── Combattimento del gatto ───────────────────────────────────────────────────

def whoosh(dur, lo, hi_start, hi_end, seed, attack=0.02):
    return env(bandpass(noise(dur, seed), lo, hi_start, hi_end), attack, dur * 0.35)


def claw_swipe(seed):
    rng = random.Random(seed)
    swish = whoosh(0.16, 500, 6000, 1200, seed)
    scratches = [(env(highpass(noise(0.025, seed + k), 2500), 0.001, 0.008), 0.02 + k * 0.022 + rng.uniform(0, 0.006), 0.6)
                 for k in range(3)]                    # tre artigli
    return mix((swish, 0, 1.0), *scratches)


def claw_swipe_crit():
    ring = bell(1760, 0.5, (1, 1.5, 2.76), (1.0, 0.7, 0.3))
    return mix((claw_swipe(10), 0, 1.0), (ring, 0.04, 0.5), (env(tone(120, 0.2, "sine", 50), 0.002, 0.06), 0.03, 0.6))


def hit(seed):
    rng = random.Random(seed)
    thump = env(tone(130 + rng.uniform(-15, 15), 0.14, "sine", 55), 0.001, 0.05)
    crack = env(lowpass(noise(0.05, seed), 2500), 0.001, 0.012)
    return drive(mix((thump, 0, 1.0), (crack, 0, 0.7)), 1.6)


def claw_heavy():
    return mix((claw_swipe(20), 0, 0.8), (hit(21), 0.03, 1.0), (bell(880, 0.4, (1, 2.3, 4.1), (0.8, 0.5, 0.3)), 0.04, 0.35))


def dodge():
    return whoosh(0.2, 300, 800, 5000, 30, attack=0.04)


def perfect_dodge():
    chime = mix(*[(note(f, 0.5, "sine", 0.25), k * 0.05, 0.5) for k, f in enumerate((NOTE["E6"], NOTE["G6"], 2093.0))])
    whom = env(tone(110, 0.7, "sine", 55), 0.05, 0.3)
    return mix((swell(chime, 0.15), 0, 0.8), (whom, 0, 0.7))


def spell_cast():
    zap = env(lowpass(tone(1400, 0.25, "square", 260, curve=0.6), 3000), 0.002, 0.09)
    sparkle = env(highpass(noise(0.2, 40), 4000), 0.002, 0.05)
    return mix((zap, 0, 0.8), (sparkle, 0, 0.4))


def spell_mark():
    return mix((bell(1320, 0.6, (1, 1.5, 3.0), (1.0, 0.6, 0.3)), 0, 1.0),
               (bell(1980, 0.5, (1, 2.0), (0.8, 0.4)), 0.06, 0.6))


def leap():
    return mix((whoosh(0.25, 400, 600, 6000, 50, attack=0.05), 0, 1.0),
               (env(tone(300, 0.2, "tri", 700), 0.01, 0.08), 0, 0.3))


def contour(dur, points):
    """Curva di frequenza a tratti: points = [(frazione, Hz), ...] interpolati in modo morbido."""
    out, N = [], n(dur)
    for i in range(N):
        u = i / max(1, N - 1)
        for (u0, f0), (u1, f1) in zip(points, points[1:]):
            if u <= u1:
                k = (u - u0) / max(1e-6, u1 - u0)
                k = k * k * (3 - 2 * k)
                out.append(f0 + (f1 - f0) * k)
                break
        else:
            out.append(points[-1][1])
    return out


def osc(freqs, harmonics=(1.0, 0.5, 0.3, 0.18, 0.1), vib=(0.0, 0.0)):
    """Voce: somma di armoniche che segue una curva di frequenza (con vibrato)."""
    out, ph = [], 0.0
    for i, f in enumerate(freqs):
        if vib[0]:
            f *= 1 + vib[1] * math.sin(TAU * vib[0] * i / SR)
        ph = (ph + f / SR) % 1.0
        out.append(sum(a * math.sin(TAU * ph * (h + 1)) for h, a in enumerate(harmonics)))
    return out


def resonate(x, freqs, q=6.0):
    """Risonatore a due poli (formante della voce) con frequenza che scorre nel tempo."""
    out, y1, y2, N = [], 0.0, 0.0, len(x)
    for i, v in enumerate(x):
        f  = freqs[min(len(freqs) - 1, i * len(freqs) // N)] if isinstance(freqs, list) else freqs
        r  = math.exp(-math.pi * f / (q * SR))
        c  = 2 * r * math.cos(TAU * f / SR)
        y  = (1 - r) * v + c * y1 - r * r * y2
        y2, y1 = y1, y
        out.append(y)
    return out


def meow(seed):
    """Miagolio di dolore ("mrIAAOW!"): voce che sale di colpo e ricade, vocale i → a → o."""
    rng  = random.Random(seed)
    dur  = rng.uniform(0.34, 0.44)
    base = rng.uniform(520, 640)
    f0   = contour(dur, [(0, base * 0.8), (0.18, base * 1.45), (0.45, base * 1.3), (1.0, base * 0.7)])
    src  = osc(f0, (1.0, 0.7, 0.5, 0.35, 0.25, 0.15, 0.1), vib=(9, 0.012))
    f1   = contour(dur, [(0, 500), (0.25, 900), (0.7, 800), (1.0, 450)])
    f2   = contour(dur, [(0, 2300), (0.25, 1700), (0.7, 1200), (1.0, 850)])
    voice = mix((resonate(src, f1, 5), 0, 1.0), (resonate(src, f2, 7), 0, 0.7), (highpass(src, 3000), 0, 0.08))
    voice = drive(swell(voice, 0.22), 1.6)
    breath = env(bandpass(noise(dur, 700 + seed), 1500, 5000), 0.02, dur * 0.4)
    return mix((voice, 0, 1.0), (breath, 0, 0.12))


def player_hurt_meow(seed):
    """Colpo subito: tonfo sordo + miagolio di dolore."""
    thump = env(tone(160, 0.15, "sine", 70), 0.001, 0.05)
    return mix((thump, 0, 0.7), (meow(seed), 0.01, 1.0))


def squeak(seed, big=False):
    """Squittio del topo colpito: un urletto acuto ("iiiik!") che scatta in alto, trema e ricade."""
    rng  = random.Random(seed)
    dur  = rng.uniform(0.32, 0.42) * (1.5 if big else 1.0)
    base = rng.uniform(2300, 2900) * (0.42 if big else 1.0)
    f0   = contour(dur, [(0, base * 0.75), (0.08, base * 1.3), (0.35, base * 1.2),
                         (0.75, base * 1.05), (1.0, base * 0.7)])
    v    = osc(f0, (1.0, 0.3, 0.1) if not big else (1.0, 0.6, 0.4, 0.25), vib=(26, 0.045))
    v    = tremolo(v, 17, 0.35)                            # voce che trema dal dolore
    v    = mix((v, 0, 1.0), (drive(v, 1.8), 0, 0.4))
    shape = [min(1.0, i / n(0.02)) * (1 - (i / len(v)) ** 2.2) for i in range(len(v))]
    v    = [a * b for a, b in zip(v, shape)]
    if big:                                                # boss: urlo rauco e grosso
        v = mix((drive(v, 2.5), 0, 1.0), (env(bandpass(noise(dur, 800 + seed), 800, 3500), 0.01, dur * 0.5), 0, 0.3))
    return v


# ── Versi del gatto ───────────────────────────────────────────────────────────

def _cat_voice(dur, f0, f1, f2, vib=(9, 0.012), drv=1.4, breath=0.1, seed=0):
    """Voce del gatto: armoniche che seguono f0, filtrate dalle formanti f1/f2."""
    src   = osc(f0, (1.0, 0.7, 0.5, 0.35, 0.25, 0.15, 0.1), vib=vib)
    voice = mix((resonate(src, f1, 5), 0, 1.0), (resonate(src, f2, 7), 0, 0.7), (highpass(src, 3000), 0, 0.06))
    voice = drive(voice, drv)
    br    = env(bandpass(noise(dur, 900 + seed), 1500, 5000), 0.01, dur * 0.5)
    return mix((voice, 0, 1.0), (br, 0, breath))


def cat_attack(seed):
    """Sul graffio (non a ogni colpo): un "mrah!" corto e deciso."""
    rng  = random.Random(seed)
    dur  = rng.uniform(0.13, 0.18)
    base = rng.uniform(560, 700)
    f0 = contour(dur, [(0, base * 0.9), (0.3, base * 1.3), (1.0, base * 0.95)])
    f1 = contour(dur, [(0, 700), (0.4, 950), (1.0, 700)])
    f2 = contour(dur, [(0, 1700), (0.4, 1500), (1.0, 1200)])
    v  = _cat_voice(dur, f0, f1, f2, drv=1.8, breath=0.18, seed=seed)
    shape = [min(1.0, i / n(0.012)) * (1 - i / len(v)) ** 1.4 for i in range(len(v))]
    return [a * b for a, b in zip(v, shape)]


def cat_dodge(seed):
    """Sulla schivata: un "hup" soffiato, quasi solo fiato."""
    rng  = random.Random(seed)
    dur  = 0.12
    base = rng.uniform(420, 520)
    f0 = contour(dur, [(0, base), (1.0, base * 1.35)])
    v  = _cat_voice(dur, f0, 600, 1300, drv=1.2, breath=0.5, seed=seed)
    return env(v, 0.006, 0.05)


def cat_hiss_short(seed):
    """Parata: soffio breve e secco."""
    rng = random.Random(seed)
    dur = rng.uniform(0.2, 0.26)
    x   = env(bandpass(noise(dur, 520 + seed), 2800, 8500), 0.008, 0.07, hold=0.05)
    return mix((tremolo(x, rng.uniform(28, 36), 0.35), 0, 1.0), (env(tone(200, 0.08, "saw", 120), 0.003, 0.03), 0, 0.25))


def cat_happy(seed):
    """Forziere, livello: trillo contento "mrrrp?" che sale alla fine."""
    rng  = random.Random(seed)
    dur  = rng.uniform(0.32, 0.4)
    base = rng.uniform(480, 560)
    f0 = contour(dur, [(0, base), (0.45, base * 1.05), (0.8, base * 1.45), (1.0, base * 1.6)])
    f1 = contour(dur, [(0, 450), (0.5, 600), (1.0, 900)])
    f2 = contour(dur, [(0, 1100), (0.5, 1400), (1.0, 2100)])
    v  = _cat_voice(dur, f0, f1, f2, vib=(6, 0.01), drv=1.3, breath=0.08, seed=seed)
    v  = tremolo(v, 24, 0.55)                                   # la "r" arrotolata
    return swell(v, 0.7)


def purr():
    """Pozione: fusa brevi (impulsi gravi a ~26 al secondo)."""
    dur  = 0.75
    body = lowpass(lowpass(noise(dur, 611), 380), 300)
    hum  = tone(52, dur, "saw")
    x    = mix((body, 0, 1.0), (lowpass(hum, 300), 0, 0.5))
    x    = tremolo(x, 26, 0.9)
    return env(x, 0.08, 0.3, hold=0.3)


def cat_sad():
    """Morte: miagolio lungo e triste che si spegne."""
    dur  = 0.95
    base = 520
    f0 = contour(dur, [(0, base * 0.95), (0.2, base * 1.2), (0.6, base * 0.95), (1.0, base * 0.6)])
    f1 = contour(dur, [(0, 500), (0.3, 850), (1.0, 420)])
    f2 = contour(dur, [(0, 2100), (0.3, 1500), (1.0, 800)])
    v  = _cat_voice(dur, f0, f1, f2, vib=(5, 0.02), drv=1.3, breath=0.1, seed=77)
    shape = [min(1.0, i / n(0.05)) * (1 - i / len(v)) ** 1.6 for i in range(len(v))]
    return [a * b for a, b in zip(v, shape)]


# ── Versi dei topi ────────────────────────────────────────────────────────────

def _chirp(f, dur, rise=1.25, vib=0.04):
    v = osc(contour(dur, [(0, f * 0.85), (0.4, f * rise), (1.0, f)]), (1.0, 0.3, 0.1), vib=(30, vib))
    shape = [min(1.0, i / n(0.006)) * (1 - i / len(v)) ** 1.5 for i in range(len(v))]
    return [a * b for a, b in zip(v, shape)]


def rat_alert(seed):
    """Ti ha visto: chiacchiericcio rapido "ki-ki-kik!"."""
    rng = random.Random(seed)
    base = rng.uniform(2700, 3500)
    k = rng.randint(2, 4)
    parts = [(_chirp(base * rng.uniform(0.92, 1.1), rng.uniform(0.035, 0.05)), i * rng.uniform(0.055, 0.07), 1.0)
             for i in range(k)]
    parts.append((_chirp(base * 1.15, 0.09, 1.35), k * 0.065, 1.0))
    return mix(*parts)


def rat_hiss(seed):
    """Carica il colpo: sibilo ruvido col muso aperto."""
    rng = random.Random(seed)
    dur = rng.uniform(0.22, 0.3)
    x   = env(bandpass(noise(dur, 830 + seed), 3200, 9500), 0.03, 0.08, hold=0.08)
    return mix((tremolo(x, rng.uniform(40, 55), 0.5), 0, 0.9),
               (_chirp(rng.uniform(2200, 2600), 0.08, 1.1, 0.08), dur * 0.5, 0.35))


def rat_attack(seed):
    """Morde: "kik!" secco e graffiato."""
    rng = random.Random(seed)
    f   = rng.uniform(2400, 3100)
    v   = _chirp(f, rng.uniform(0.08, 0.11), 1.4, 0.06)
    return mix((drive(v, 2.2), 0, 0.9), (env(highpass(noise(0.03, 840 + seed), 3000), 0.001, 0.01), 0, 0.3))


def player_death():
    fall = env(lowpass(tone(620, 0.9, "square", 90, curve=0.7), 1800), 0.01, 0.4, hold=0.2)
    return mix((fall, 0, 0.7), (env(lowpass(noise(0.6, 61), 600), 0.01, 0.2), 0.3, 0.5))


def level_up():
    seq = [NOTE["C5"], NOTE["E5"], NOTE["G5"], NOTE["C6"]]
    parts = [(note(f, 0.18, "square", 0.08), k * 0.07, 0.35) for k, f in enumerate(seq)]
    chord = mix(*[(note(f, 0.6, "tri", 0.3), 0, 0.4) for f in (NOTE["C6"], NOTE["E6"], NOTE["G6"])])
    return mix(*parts, (lowpass(chord, 4000), 0.28, 1.0))


# ── Loot e forziere ───────────────────────────────────────────────────────────

def coin(seed):
    base = 1.0 + (seed - 1) * 0.04
    return mix((note(NOTE["B5"] * base, 0.07, "square", 0.04), 0, 0.5),
               (note(NOTE["E6"] * base, 0.25, "square", 0.1), 0.06, 0.5))


def orb():
    return env(tone(660, 0.12, "sine", 1320, curve=0.5), 0.003, 0.04)


def parry_swing():
    return whoosh(0.12, 800, 6000, 2500, 300, attack=0.01)


def parry():
    ting = bell(1975, 0.6, (1, 2.4, 3.9), (1.0, 0.6, 0.3))
    ping = env(tone(1200, 0.25, "sine", 2400, curve=0.4), 0.002, 0.08)
    return mix((ting, 0, 0.9), (ping, 0, 0.5), (env(highpass(noise(0.03, 301), 3000), 0.0005, 0.008), 0, 0.6))


def potion():
    blips = [(env(tone(f, 0.07, "sine", f * 1.6), 0.005, 0.03), k * 0.075, 0.8)
             for k, f in enumerate((300, 360, 430, 520))]
    return mix(*blips)


def potion_mana():
    return mix((potion(), 0, 0.8), (bell(1568, 0.4, (1, 2.0), (0.8, 0.4)), 0.2, 0.3))


def chest():
    creak = env(lowpass(tone(110, 0.35, "saw", 160, vibrato=(18, 0.08)), 900), 0.03, 0.2)
    rng = random.Random(70)
    jingle = [(bell(rng.uniform(2000, 3200), 0.25, (1, 2.4), (0.7, 0.3)), 0.25 + k * 0.05, 0.4) for k in range(6)]
    return mix((creak, 0, 0.8), *jingle)


# ── Stanze e porte ────────────────────────────────────────────────────────────

def door_lock():
    clang = bell(196, 0.9, (1, 2.92, 4.7, 6.3), (1.0, 0.6, 0.4, 0.25))
    thud  = env(tone(70, 0.25, "sine", 40), 0.002, 0.08)
    return drive(mix((clang, 0, 1.0), (thud, 0, 0.9), (env(lowpass(noise(0.08, 80), 3000), 0.001, 0.02), 0, 0.5)), 1.3)


def door_open():
    clank = bell(330, 0.4, (1, 2.7, 5.1), (0.6, 0.4, 0.2))
    rise  = env(tone(392, 0.3, "tri", 784), 0.02, 0.15)
    return mix((clank, 0, 0.8), (rise, 0.05, 0.4))


def room_clear():
    return mix((note(NOTE["G5"], 0.15, "tri", 0.07), 0, 0.6), (note(NOTE["C6"], 0.4, "tri", 0.2), 0.1, 0.6))


def floor_complete():
    seq = [NOTE["C5"], NOTE["E5"], NOTE["G5"], NOTE["C6"]]
    parts = [(note(f, 0.2, "square", 0.1), k * 0.12, 0.3) for k, f in enumerate(seq)]
    chord = mix(*[(note(f, 1.0, "tri", 0.5), 0, 0.4) for f in (NOTE["C5"], NOTE["E5"], NOTE["G5"], NOTE["C6"])])
    return mix(*parts, (lowpass(chord, 3500), 0.5, 1.0))


def recall():
    sweep = mix(*[(swell(tone(f, 0.7, "sine", f * 3, curve=1.5)), k * 0.04, 0.4) for k, f in enumerate((220, 330, 440))])
    return mix((tremolo(sweep, 14, 0.5), 0, 1.0), (whoosh(0.7, 300, 500, 6000, 90, attack=0.3), 0, 0.4))


# ── Nemici ────────────────────────────────────────────────────────────────────

def enemy_swing():
    return whoosh(0.13, 400, 3500, 900, 100, attack=0.015)


def enemy_death(seed):
    """Topo abbattuto: squittio acuto che si spezza e cade, poi lo sbuffo."""
    rng = random.Random(seed)
    f0  = rng.uniform(2300, 2900)
    dur = rng.uniform(0.32, 0.4)
    fc  = contour(dur, [(0, f0 * 0.9), (0.1, f0 * 1.25), (0.4, f0 * 1.1), (1.0, f0 * 0.45)])
    sq  = tremolo(osc(fc, (1.0, 0.35, 0.12), vib=(24, 0.06)), 19, 0.4)
    shape = [min(1.0, i / n(0.01)) * (1 - i / len(sq)) ** 1.8 for i in range(len(sq))]
    sq  = [a * b for a, b in zip(sq, shape)]
    poof = env(lowpass(noise(0.3, seed), 1200, 300), 0.01, 0.1)
    return mix((sq, 0, 0.55), (poof, 0.06, 0.7))


def sling():
    whirr = env(bandpass(noise(0.22, 115), 300, 1200, 3000), 0.05, 0.06, hold=0.1)
    snap  = env(highpass(noise(0.02, 116), 2500), 0.0005, 0.005)
    return mix((tremolo(whirr, 22, 0.7), 0, 0.7), (snap, 0.17, 0.9), (whoosh(0.12, 500, 4000, 1500, 117), 0.17, 0.5))


def tell():
    """Avviso di un attacco nemico: breve 'shing' metallico."""
    return mix((bell(2600, 0.3, (1, 1.5), (0.6, 0.3)), 0, 0.7),
               (env(highpass(noise(0.05, 400), 5000), 0.002, 0.02), 0, 0.4))


def knife_draw():
    """I 5 coltelli del boss si sollevano: cinque 'shing' in salita."""
    parts = [(bell(2200 + k * 260, 0.35, (1, 1.5, 2.7), (0.7, 0.35, 0.2), seed=k), k * 0.07, 0.55)
             for k in range(5)]
    parts.append((env(highpass(noise(0.4, 410), 4000), 0.05, 0.15, hold=0.1), 0, 0.25))
    return mix(*parts)


def knife_throw():
    """Raffica di coltelli: fruscii acuti e sfalsati."""
    return mix(*[(whoosh(0.16, 900, 6000, 2000, 420 + k, attack=0.005), k * 0.025, 0.55) for k in range(5)])


def spell_blade():
    """Graffio Spettrale: tre fruscii cristallini."""
    return mix(*[(mix((whoosh(0.18, 1500, 7000, 2500, 500 + k, attack=0.004), 0, 0.7),
                      (bell(1800 + k * 300, 0.25, (1, 2.1), (0.5, 0.3)), 0, 0.25)), k * 0.035, 0.7) for k in range(3)])


def hiss():
    """Soffio del gatto: sibilo rabbioso."""
    x = env(bandpass(noise(0.45, 510), 2500, 8000), 0.02, 0.18, hold=0.12)
    return mix((tremolo(x, 31, 0.3), 0, 1.0), (env(tone(180, 0.2, "saw", 90), 0.005, 0.06), 0, 0.3))


def dark_sight():
    """Occhi nel Buio: bagliore basso che si apre."""
    pad = swell(mix((tone(220, 0.8, "sine", 440), 0, 0.5), (tone(330, 0.8, "sine", 660), 0, 0.35)), 0.3)
    return mix((pad, 0, 1.0), (bell(1320, 0.6, (1, 1.5), (0.6, 0.3)), 0.15, 0.4))


def shadow():
    """Ombra Felina: soffio scuro."""
    return mix((whoosh(0.5, 200, 400, 2500, 520, attack=0.1), 0, 0.8),
               (env(tone(140, 0.4, "sine", 90), 0.05, 0.15), 0, 0.5))


def nine_lives():
    """Nove Vite: campanelle che salgono."""
    return mix(*[(bell(880 * 2 ** (k / 12 * 3), 0.5, (1, 2.4), (0.6, 0.3), seed=k), k * 0.05, 0.4) for k in range(5)])


def nine_lives_save():
    """Colpo mortale evitato: accordo luminoso."""
    return mix(*[(bell(f, 1.0, (1, 2.0, 3.0), (1.0, 0.5, 0.3)), 0, 0.4) for f in (660, 880, 1320)])


def audacia_up():
    """Scaglione di Audacia: fiammata che sale + accordo."""
    flame = env(bandpass(noise(0.6, 600), 300, 1500, 5000), 0.1, 0.25, hold=0.1)
    chord = mix(*[(note(f, 0.7, "tri"), 0.08 * k, 0.35) for k, f in enumerate((392, 523.25, 659.25, 783.99))])
    return mix((flame, 0, 0.6), (chord, 0.05, 1.0))


def audacia_tick():
    """+1 Audacia: piccolo scoppiettio."""
    return mix((env(bandpass(noise(0.12, 610), 800, 4000), 0.005, 0.04), 0, 0.6),
               (note(784, 0.15, "tri"), 0.01, 0.4))


def rock_fall():
    whistle = env(tone(1400, 1.0, "sine", 300, curve=1.6), 0.1, 0.5, hold=0.3)
    return mix((whistle, 0, 0.35), (whoosh(1.0, 200, 400, 1500, 401, attack=0.6), 0, 0.5))


def rock_impact():
    boom = env(tone(65, 0.6, "sine", 30), 0.002, 0.22)
    debris = env(lowpass(noise(0.5, 402), 1800, 400), 0.002, 0.12)
    return drive(mix((boom, 0, 1.0), (debris, 0, 0.8)), 1.8)


def alarm():
    beeps = [(note(f, 0.12, "square", 0.1), k * 0.14, 0.35) for k, f in enumerate((880, 660, 880, 660))]
    return lowpass(mix(*beeps), 3500)


def reinforce():
    drums = [(env(tone(90, 0.2, "sine", 45), 0.002, 0.07), k * 0.18, 1.0) for k in range(2)]
    return mix(*drums, (env(lowpass(noise(0.15, 110), 800), 0.002, 0.04), 0, 0.4))


def channel():
    hum = mix((tone(220, 0.8, "sine"), 0, 0.5), (tone(330, 0.8, "sine", vibrato=(5, 0.01)), 0, 0.35),
              (tone(440, 0.8, "tri"), 0, 0.15))
    return swell(tremolo(hum, 7, 0.4), 0.3)


def growl(dur, freq, seed, rise=1.0):
    rng = random.Random(seed)
    base = tone(freq, dur, "saw", freq * rise, vibrato=(rng.uniform(22, 30), 0.08))
    rough = lowpass(noise(dur, seed), 900)
    body = [b * (0.6 + 0.6 * abs(r)) for b, r in zip(base, rough)]   # ruvidità
    return drive(lowpass(body, 1100), 2.0)


def frenzy():
    return env(growl(0.45, 95, 120), 0.04, 0.2, hold=0.1)


# ── Boss ──────────────────────────────────────────────────────────────────────

def boss_growl():
    return env(growl(0.7, 62, 130, 0.9), 0.08, 0.3, hold=0.2)


def boss_charge():
    stomp = env(tone(70, 0.3, "sine", 35), 0.002, 0.1)
    return mix((stomp, 0, 1.0), (whoosh(0.4, 150, 600, 2500, 131, attack=0.05), 0.05, 0.8))


def boss_stun():
    clang = bell(147, 1.0, (1, 2.92, 4.7, 6.3), (1.0, 0.6, 0.4, 0.25))
    bonk  = env(tone(220, 0.15, "sine", 90), 0.002, 0.05)
    tweets = [(env(tone(3000, 0.07, "sine", 3800), 0.005, 0.03), 0.35 + k * 0.12, 0.25) for k in range(3)]
    return mix((drive(clang, 1.4), 0, 0.8), (bonk, 0, 0.9), *tweets)


def boss_tail():
    crack = env(highpass(noise(0.03, 150), 1500), 0.0005, 0.006)
    return mix((whoosh(0.3, 300, 900, 4500, 151, attack=0.08), 0, 0.8), (crack, 0.22, 1.0))


def boss_roar():
    return env(growl(1.2, 70, 160, 1.35), 0.12, 0.45, hold=0.4)


def boss_smash():
    return mix((hit(170), 0, 1.0), (env(lowpass(noise(0.5, 171), 400), 0.002, 0.15), 0, 0.8),
               (env(tone(55, 0.5, "sine", 35), 0.002, 0.18), 0, 0.9))


def boss_shot():
    fire = env(bandpass(noise(0.4, 175), 200, 2500, 600), 0.005, 0.12)
    boom = env(tone(160, 0.25, "saw", 60), 0.002, 0.08)
    return drive(mix((fire, 0, 0.9), (lowpass(boom, 900), 0, 0.7)), 1.5)


def boss_death():
    roar = env(growl(1.4, 80, 180, 0.45), 0.05, 0.5, hold=0.3)
    rumble = env(lowpass(noise(1.6, 181), 250), 0.1, 0.6)
    return mix((roar, 0, 0.9), (rumble, 0.3, 0.8))


# ── Interfaccia ───────────────────────────────────────────────────────────────

def ui_open():
    return mix((env(highpass(noise(0.012, 200), 3000), 0.0005, 0.004), 0, 0.6),
               (note(1200, 0.06, "sine", 0.02), 0, 0.4))


def page():
    return env(bandpass(noise(0.15, 210), 1500, 6000, 2500), 0.03, 0.04)


def buy():
    return mix((coin(1), 0, 0.8), (bell(2637, 0.5, (1, 2.0, 3.0), (0.9, 0.5, 0.3)), 0.1, 0.6))


def error():
    buzz = [(env(lowpass(tone(140, 0.1, "square"), 1200), 0.003, 0.06, hold=0.04), k * 0.12, 0.6) for k in range(2)]
    return mix(*buzz)


SOUNDS = {
    "claw_swipe_1": lambda: claw_swipe(1), "claw_swipe_2": lambda: claw_swipe(2), "claw_swipe_3": lambda: claw_swipe(3),
    "claw_swipe_crit": claw_swipe_crit, "claw_heavy": claw_heavy,
    "hit_1": lambda: hit(1), "hit_2": lambda: hit(2), "hit_3": lambda: hit(3),
    "dodge": dodge, "perfect_dodge": perfect_dodge,
    "spell_cast": spell_cast, "spell_mark": spell_mark, "leap": leap,
    "meow_1": lambda: player_hurt_meow(1), "meow_2": lambda: player_hurt_meow(2), "meow_3": lambda: player_hurt_meow(3),
    "squeak_1": lambda: squeak(1), "squeak_2": lambda: squeak(2), "squeak_3": lambda: squeak(3),
    "squeak_4": lambda: squeak(4), "squeak_big_1": lambda: squeak(11, True), "squeak_big_2": lambda: squeak(12, True), "player_death": player_death, "level_up": level_up,
    "coin_1": lambda: coin(1), "coin_2": lambda: coin(2), "coin_3": lambda: coin(3),
    "potion": potion, "orb": orb, "parry_swing": parry_swing, "parry": parry, "potion_mana": potion_mana, "chest": chest,
    "door_lock": door_lock, "door_open": door_open, "room_clear": room_clear,
    "floor_complete": floor_complete, "recall": recall,
    "enemy_swing": enemy_swing, "enemy_death_1": lambda: enemy_death(1), "enemy_death_2": lambda: enemy_death(2),
    "sling": sling, "boss_shot": boss_shot, "tell": tell, "rock_fall": rock_fall, "rock_impact": rock_impact,
    "alarm": alarm, "reinforce": reinforce, "channel": channel, "frenzy": frenzy,
    "boss_growl": boss_growl, "boss_charge": boss_charge, "boss_stun": boss_stun,
    "boss_tail": boss_tail, "boss_roar": boss_roar, "boss_smash": boss_smash, "boss_death": boss_death,
    "knife_draw": knife_draw, "audacia_up": audacia_up, "audacia_tick": audacia_tick, "spell_blade": spell_blade, "hiss": hiss, "dark_sight": dark_sight,
    "shadow": shadow, "nine_lives": nine_lives, "nine_lives_save": nine_lives_save, "knife_throw": knife_throw,
    "ui_open": ui_open, "page": page, "buy": buy, "error": error,
    "enemy_death_3": lambda: enemy_death(3),
    "cat_attack_1": lambda: cat_attack(1), "cat_attack_2": lambda: cat_attack(2),
    "cat_attack_3": lambda: cat_attack(3), "cat_attack_4": lambda: cat_attack(4),
    "cat_dodge_1": lambda: cat_dodge(1), "cat_dodge_2": lambda: cat_dodge(2),
    "cat_hiss_1": lambda: cat_hiss_short(1), "cat_hiss_2": lambda: cat_hiss_short(2),
    "cat_happy_1": lambda: cat_happy(1), "cat_happy_2": lambda: cat_happy(2),
    "purr": purr, "cat_sad": cat_sad,
    "rat_alert_1": lambda: rat_alert(1), "rat_alert_2": lambda: rat_alert(2),
    "rat_alert_3": lambda: rat_alert(3), "rat_alert_4": lambda: rat_alert(4),
    "rat_hiss_1": lambda: rat_hiss(1), "rat_hiss_2": lambda: rat_hiss(2), "rat_hiss_3": lambda: rat_hiss(3),
    "rat_attack_1": lambda: rat_attack(1), "rat_attack_2": lambda: rat_attack(2), "rat_attack_3": lambda: rat_attack(3),
}

if __name__ == "__main__":
    import sys
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    only = sys.argv[1:]          # es. "cat_" "rat_": rigenera solo i suoni che iniziano così
    for name, fn in SOUNDS.items():
        if only and not any(name.startswith(o) for o in only):
            continue
        x = fn()
        save(name, x)
        print(f"{name:18s} {len(x) / SR:5.2f}s")
    print(f"{len(SOUNDS)} suoni salvati in {OUT_DIR}")
