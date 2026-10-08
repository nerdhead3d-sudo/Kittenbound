"""Impostazioni del giocatore (menu Impostazioni): settings.json accanto ai salvataggi.

Non è cifrato: sono solo preferenze (schermo, grafica, luminosità, volume).
"""
import json
import os

from game import save

DEFAULTS = {
    "fullscreen": True,
    "quality":    0,        # 0 = automatica, 1 = 720p, 2 = 1440p, 3 = 2160p (al riavvio)
    "brightness": 0,        # 0 normale, 1 più chiara, 2 molto chiara (meno buio nel dungeon)
    "volume":     8,        # 0-10
    "show_fps":   False,
}
QUALITY_NAMES    = ["Automatica", "Normale (720p)", "Alta (1440p)", "Massima (2160p)"]
BRIGHTNESS_NAMES = ["Normale", "Più chiara", "Molto chiara"]
BRIGHTNESS_DARK  = [1.0, 0.96, 0.92]          # moltiplica il buio del dungeon

_values = dict(DEFAULTS)


def _path():
    return save.save_dir() / "settings.json"


def load() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        for k, v in data.items():
            if k in DEFAULTS and isinstance(v, type(DEFAULTS[k])):
                _values[k] = v
    except (OSError, ValueError):
        pass
    _values["quality"]    = max(0, min(3, _values["quality"]))
    _values["brightness"] = max(0, min(2, _values["brightness"]))
    _values["volume"]     = max(0, min(10, _values["volume"]))
    return _values


def write():
    try:
        save.save_dir().mkdir(parents=True, exist_ok=True)
        _path().write_text(json.dumps(_values, indent=2), encoding="utf-8")
    except OSError:
        pass


def get(key: str):
    return _values[key]


def set(key: str, value):
    _values[key] = value
    write()


def apply_quality_env():
    """La qualità sceglie la risoluzione di disegno (gfx.K) all'avvio. KITTEN_HD, se c'è già
    (test), ha la precedenza."""
    q = _values["quality"]
    if q and "KITTEN_HD" not in os.environ:
        os.environ["KITTEN_HD"] = str(q)
