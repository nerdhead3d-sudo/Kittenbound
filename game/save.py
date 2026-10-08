"""Salvataggio automatico, cifrato e firmato.

Tre slot (%APPDATA%/Kittenbound/slot1.dat ... slot3.dat), ognuno una partita a sé con un
solo file riscritto di continuo: non si può tornare indietro. Il contenuto (JSON compresso)
è cifrato, così aperto con un editor non si legge, e firmato con HMAC-SHA256: se qualcuno
cambia anche un byte la firma non torna e il file viene scartato (si prova la copia precedente, slotN.bak).

Ferma chi prova a cambiare i numeri a mano; non chi decompila il gioco per trovare la
chiave: per un gioco offline non si può fare di più.

KITTEN_SAVE_DIR cambia la cartella (per i test, così non toccano il salvataggio vero).
"""
import hashlib
import hmac
import json
import os
import zlib
from pathlib import Path

VERSION = 1
_MAGIC  = b"KTB1"
_KEY    = hashlib.sha256(b"Kittenbound/save/" + bytes.fromhex(
    "9f3c5ab1e07246d8b21c4e6f0a9d73c58e1b26f4d0c7a3958b6e12f0c4d7a9e3")).digest()


def save_dir() -> Path:
    override = os.environ.get("KITTEN_SAVE_DIR")
    if override:
        return Path(override)
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "Kittenbound"


SLOTS = 3


def save_path(slot: int) -> Path:
    return save_dir() / f"slot{slot}.dat"


def _migrate():
    """Il primo salvataggio (save.dat, prima degli slot) diventa lo slot 1."""
    old = save_dir() / "save.dat"
    if old.exists() and not save_path(1).exists():
        try:
            os.replace(old, save_path(1))
            if (save_dir() / "save.bak").exists():
                os.replace(save_dir() / "save.bak", save_dir() / "slot1.bak")
        except OSError:
            pass


def _keystream(nonce: bytes, n: int) -> bytes:
    out, counter = bytearray(), 0
    while len(out) < n:
        out += hashlib.sha256(_KEY + nonce + counter.to_bytes(8, "little")).digest()
        counter += 1
    return bytes(out[:n])


def encode(data: dict) -> bytes:
    raw    = zlib.compress(json.dumps(data, separators=(",", ":")).encode("utf-8"), 9)
    nonce  = os.urandom(16)
    cipher = bytes(a ^ b for a, b in zip(raw, _keystream(nonce, len(raw))))
    body   = _MAGIC + nonce + cipher
    return body + hmac.new(_KEY, body, hashlib.sha256).digest()


def decode(blob: bytes) -> "dict | None":
    """Il contenuto, oppure None se il file è rovinato o è stato modificato."""
    if len(blob) < len(_MAGIC) + 16 + 32 or not blob.startswith(_MAGIC):
        return None
    body, sig = blob[:-32], blob[-32:]
    if not hmac.compare_digest(sig, hmac.new(_KEY, body, hashlib.sha256).digest()):
        return None
    nonce, cipher = body[len(_MAGIC):len(_MAGIC) + 16], body[len(_MAGIC) + 16:]
    try:
        raw  = bytes(a ^ b for a, b in zip(cipher, _keystream(nonce, len(cipher))))
        data = json.loads(zlib.decompress(raw).decode("utf-8"))
    except (zlib.error, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("version") == VERSION else None


def write(slot: int, data: dict) -> bool:
    """Scrive in modo sicuro: prima un file temporaneo, poi lo sostituisce (la versione
    precedente resta come slotN.bak). Se il disco non collabora il gioco va avanti lo stesso."""
    try:
        folder = save_dir()
        folder.mkdir(parents=True, exist_ok=True)
        path, tmp, bak = save_path(slot), folder / f"slot{slot}.tmp", folder / f"slot{slot}.bak"
        tmp.write_bytes(encode({**data, "version": VERSION}))
        if path.exists():
            os.replace(path, bak)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def read(slot: int) -> "dict | None":
    """Il salvataggio valido più recente dello slot (slotN.dat, altrimenti slotN.bak), o None."""
    _migrate()
    for name in (f"slot{slot}.dat", f"slot{slot}.bak"):
        try:
            data = decode((save_dir() / name).read_bytes())
        except OSError:
            continue
        if data is not None:
            return data
    return None


def delete(slot: int):
    for name in (f"slot{slot}.dat", f"slot{slot}.bak", f"slot{slot}.tmp"):
        try:
            (save_dir() / name).unlink()
        except OSError:
            pass
