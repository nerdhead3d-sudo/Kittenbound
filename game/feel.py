"""Sensazione dei colpi: scuotimento dello schermo e hit-stop (pochi fotogrammi di pausa).

Chiunque può chiamare shake() / hitstop(); main.py chiede offset() per la telecamera e
frozen() per sapere se il mondo va fermato in questo fotogramma.
"""
import math

from game import user_settings as us

_trauma = 0.0          # 0-1: quanto trema (lo scuotimento è trauma², così i colpi piccoli si sentono poco)
_stop   = 0.0          # secondi di hit-stop rimasti
_t      = 0.0

MAX_OFFSET = 9.0       # pixel logici al massimo
DECAY      = 2.2       # trauma perso al secondo


def shake(amount: float):
    global _trauma
    _trauma = min(1.0, _trauma + amount)


def hitstop(seconds: float):
    global _stop
    _stop = max(_stop, seconds)


def reset():
    global _trauma, _stop
    _trauma, _stop = 0.0, 0.0


def tick(dt: float) -> bool:
    """Avanza il tempo; True se questo fotogramma il mondo resta fermo (hit-stop)."""
    global _trauma, _stop, _t
    _t += dt
    _trauma = max(0.0, _trauma - DECAY * dt)
    if _stop > 0:
        _stop = max(0.0, _stop - dt)
        return True
    return False


def offset() -> tuple:
    """Spostamento della telecamera in questo istante (0, 0 se lo scuotimento è spento)."""
    if _trauma <= 0 or not us.get("shake"):
        return 0, 0
    k = _trauma * _trauma * MAX_OFFSET
    # due onde sfasate per asse: un tremolio irregolare ma morbido (niente salti casuali)
    x = math.sin(_t * 61.0) * 0.6 + math.sin(_t * 97.0 + 1.3) * 0.4
    y = math.sin(_t * 73.0 + 2.1) * 0.6 + math.sin(_t * 89.0 + 0.4) * 0.4
    return round(x * k), round(y * k)
