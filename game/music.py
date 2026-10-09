"""Musica di sottofondo: un brano per l'hub, uno per il dungeon, uno per il boss.

I brani sono in assets/music/<nome>.ogg o .wav (generati da tools/generate_music.py, ma si
possono sostituire con brani veri con lo stesso nome). Cambiando brano si dissolvono uno
nell'altro su due canali riservati, così gli effetti non li interrompono mai.
"""
from pathlib import Path

import pygame

from game import user_settings as us

_DIR  = Path(__file__).resolve().parent.parent / "assets" / "music"
FADE_MS = 1400
BASE    = 0.55          # la musica sta sotto agli effetti


class Music:
    _instance = None

    @classmethod
    def get(cls) -> "Music":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.enabled  = pygame.mixer.get_init() is not None
        self.current  = None
        self._tracks  = {}
        self._chan    = None
        self._muted   = False
        if not self.enabled:
            return
        pygame.mixer.set_reserved(2)                   # canali 0 e 1: solo musica
        self._channels = [pygame.mixer.Channel(0), pygame.mixer.Channel(1)]
        self._which    = 0

    def _track(self, name):
        if name not in self._tracks:
            snd = None
            for ext in (".ogg", ".wav"):
                path = _DIR / f"{name}{ext}"
                if path.exists():
                    try:
                        snd = pygame.mixer.Sound(str(path))
                    except pygame.error:
                        snd = None
                    break
            self._tracks[name] = snd
        return self._tracks[name]

    def volume(self) -> float:
        return 0.0 if self._muted else BASE * us.get("music") / 10

    def play(self, name):
        """Passa al brano `name` (None = silenzio). Non fa niente se è già quello."""
        if not self.enabled or name == self.current:
            return
        self.current = name
        old = self._channels[self._which]
        old.fadeout(FADE_MS)
        snd = self._track(name) if name else None
        if snd is None:
            return
        self._which = 1 - self._which
        ch = self._channels[self._which]
        ch.stop()
        ch.set_volume(self.volume())
        ch.play(snd, loops=-1, fade_ms=FADE_MS)

    def set_muted(self, muted: bool):
        self._muted = muted
        if not muted:                 # il muto ferma tutti i canali: si riparte al prossimo frame
            self.current = None
        self.refresh()

    def refresh(self):
        """Volume cambiato nelle impostazioni (o muto)."""
        if self.enabled:
            ch = self._channels[self._which]
            if ch.get_busy():
                ch.set_volume(self.volume())
