"""Renderizza un oggetto 3D (arma, effetto) disteso orizzontale in N direzioni,
con la stessa camera 3/4 dei personaggi. Il perno (es. il manico) sta al centro del frame,
così nel gioco basta disegnare il frame centrato sulla mano di chi lo usa.

Uso (da terminale, nella root del progetto):
    blender -b --python tools/render_prop_sprites.py -- <modello.glb> <nome> [cartella_output] [--preview]
        [--dirs=N] [--res=PX] [--ortho=U] [--tip]

--tip: oggetti da lancio (es. coltello): la punta (punto più basso del modello) guarda nella
direzione del frame e il perno è il centro dell'oggetto invece del manico.

Output: assets/sprites/fx_<nome>.png — strip orizzontale di DIRECTIONS frame quadrati;
frame i = oggetto rivolto verso la direzione schermo i * 360/DIRECTIONS gradi (0 = est, senso orario).
Pensato per oggetti piatti: il manico è il punto più basso del modello e il resto si stende
dal manico verso l'esterno.
"""
import math
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sprite_common as sc                                     # noqa: E402

OPTS = {k: v for k, _, v in (a[2:].partition("=") for a in sys.argv if a.startswith("--") and a != "--preview" and a != "--")}
sys.argv = [a for a in sys.argv if not (a.startswith("--") and a[2:].partition("=")[0] in OPTS)]

DIRECTIONS = int(OPTS.get("dirs", 16))
FRAME_RES  = int(OPTS.get("res", 220))      # px per frame nel gioco
ORTHO      = float(OPTS.get("ortho", 4.4))  # unità coperte dal frame (perno al centro)
TIP        = "tip" in OPTS
RENDER_RES = 512

(src, name), out_dir, PREVIEW = sc.parse_args(2)
ob, co, H = sc.load_model(Path(src))

# Perno = manico (punto più basso del modello, dove sta l'anello)
pivot = co[np.argmin(co[:, 2])].copy()
co -= pivot
# Stendi l'oggetto a terra: il piano verticale XZ diventa il piano orizzontale XY
co = np.stack([co[:, 0], co[:, 2], -co[:, 1]], axis=1)
# Allinea l'asse principale (manico → baricentro delle code) con +X
reach = co[np.linalg.norm(co, axis=1) > np.percentile(np.linalg.norm(co, axis=1), 60)].mean(axis=0)
ang   = math.atan2(reach[1], reach[0])
c, s_ = math.cos(-ang), math.sin(-ang)
co = np.stack([co[:, 0] * c - co[:, 1] * s_, co[:, 0] * s_ + co[:, 1] * c, co[:, 2]], axis=1)
if TIP:                                               # punta in avanti, perno al centro
    co[:, :2] *= -1
    co[:, 0] -= (co[:, 0].min() + co[:, 0].max()) / 2
    co[:, 1] -= (co[:, 1].min() + co[:, 1].max()) / 2
    co[:, 2] -= (co[:, 2].min() + co[:, 2].max()) / 2
ob.data.vertices.foreach_set("co", co.ravel())
ob.data.update()

scene = sc.SpriteScene(0.0, ORTHO)                    # camera puntata sul perno (altezza 0)
scene.sc.render.resolution_x = scene.sc.render.resolution_y = RENDER_RES
scene.sc.view_settings.exposure = 0.0

ob.rotation_mode = 'XYZ'                              # l'import glTF usa i quaternioni
tmp, frames = out_dir / "_tmp_render.png", []
for i in range(DIRECTIONS):
    a = i * 360 / DIRECTIONS
    ob.rotation_euler = (0, 0, math.radians(-a))      # direzione schermo a → mondo (cos a, -sin a)
    bpy.context.view_layer.update()
    frames.append(scene.render(tmp, RENDER_RES if PREVIEW else FRAME_RES))
tmp.unlink(missing_ok=True)
out = out_dir / (f"preview_fx_{name}.png" if PREVIEW else f"fx_{name}.png")
sc.save_png(out, np.concatenate(frames, axis=1))
print(f"Salvato {out}")
