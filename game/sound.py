import random
from pathlib import Path

import pygame

from game import settings as s

# Effetti generati da tools/generate_sounds.py. Un suono con varianti è salvato come
# <nome>_1.wav, <nome>_2.wav, ...: play("<nome>") ne sceglie una a caso.
_SOUNDS_DIR = Path(__file__).resolve().parent.parent / "assets" / "sounds"


class SoundManager:
    """Singleton. Carica gli effetti sonori e li riproduce.
    Se l'audio non è disponibile (nessun dispositivo, mixer non inizializzato)
    tutte le chiamate diventano silenziose: il gioco funziona lo stesso."""

    _instance = None

    @classmethod
    def get(cls) -> "SoundManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.muted   = False
        self.master  = 1.0          # volume generale (menu Impostazioni), 0-1
        self._sounds: dict[str, list[pygame.mixer.Sound]] = {}
        self._last_ms: dict[str, int] = {}
        self.enabled = pygame.mixer.get_init() is not None
        if not self.enabled:
            return
        pygame.mixer.set_num_channels(s.SFX_CHANNELS)
        for path in sorted(_SOUNDS_DIR.glob("*.wav")):
            stem = path.stem
            base, _, idx = stem.rpartition("_")
            name = base if idx.isdigit() and base else stem
            try:
                self._sounds.setdefault(name, []).append(pygame.mixer.Sound(str(path)))
            except pygame.error:
                pass

    def play(self, name: str, volume: float = 1.0):
        """Riproduce un effetto; lo stesso suono non riparte prima di SFX_MIN_GAP_MS
        (evita il rumore quando molti eventi uguali capitano nello stesso frame)."""
        if not self.enabled or self.muted:
            return
        variants = self._sounds.get(name)
        if not variants:
            return
        now = pygame.time.get_ticks()
        if now - self._last_ms.get(name, -10_000) < s.SFX_MIN_GAP_MS:
            return
        self._last_ms[name] = now
        channel = random.choice(variants).play()
        if channel is not None:
            channel.set_volume(max(0.0, min(1.0, volume * s.SFX_VOLUME * self.master)))

    def toggle_mute(self) -> bool:
        self.muted = not self.muted
        if self.muted and self.enabled:
            pygame.mixer.stop()
        return self.muted


def play(name: str, volume: float = 1.0):
    """Scorciatoia: from game.sound import play; play("coin")."""
    SoundManager.get().play(name, volume)


def voice(name: str, chance: float, volume: float = 1.0):
    """Verso (gatto o topi) solo ogni tanto, così non stanca: chance = probabilità 0-1."""
    if random.random() < chance:
        SoundManager.get().play(name, volume)
