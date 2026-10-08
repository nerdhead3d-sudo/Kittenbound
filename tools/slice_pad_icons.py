"""Ritaglia le icone dei tasti PlayStation da un'immagine unica (sfondo trasparente).

Uso: python tools/slice_pad_icons.py <immagine.png>
Scrive assets/sprites/pad/<nome>.png (max 128 px di lato, bordi trasparenti tolti).
"""
import sys
from pathlib import Path
from PIL import Image

OUT = Path(__file__).resolve().parent.parent / "assets" / "sprites" / "pad"
# zone approssimative (x0, y0, x1, y1) sull'immagine 1774x887; il bordo vero lo trova l'alpha
BOXES = {
    "triangle": (40, 20, 235, 205),  "circle": (238, 20, 432, 205),
    "cross": (435, 20, 630, 205),    "square": (633, 20, 828, 205),
    "ps": (830, 20, 1025, 205),
    "up": (1100, 35, 1252, 195),     "down": (1256, 35, 1408, 195),
    "left": (1412, 35, 1568, 195),   "right": (1572, 35, 1725, 195),
    "l1": (50, 210, 365, 400),       "r1": (372, 210, 685, 400),
    "l2": (700, 205, 945, 450),      "r2": (955, 205, 1200, 450),
    "l3": (1220, 220, 1455, 450),    "r3": (1480, 220, 1715, 450),
    "share": (70, 455, 375, 565),    "options": (398, 455, 705, 565),
    "dpad": (80, 570, 385, 855),     "dpad_arrows": (465, 570, 770, 855),
    "stick_l": (915, 575, 1205, 865), "stick_r": (1335, 575, 1625, 865),
}

src = Image.open(sys.argv[1]).convert("RGBA")
OUT.mkdir(parents=True, exist_ok=True)
for name, box in BOXES.items():
    tile  = src.crop(box)
    alpha = tile.getchannel("A").point(lambda a: 255 if a > 40 else 0)
    tile  = tile.crop(alpha.getbbox())
    tile.thumbnail((128, 128), Image.LANCZOS)
    tile.save(OUT / f"{name}.png")
    print(name, tile.size)
