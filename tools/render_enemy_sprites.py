"""Genera gli sprite dei nemici bipedi (topi, boss) da un modello 3D con Blender:
scheletro automatico da bipede + camminata + attacco con l'arma, 8 direzioni,
vista 3/4 dall'alto. Un modello può produrre più nemici ricolorando i vestiti.

Uso (da terminale, nella root del progetto):
    blender -b --python tools/render_enemy_sprites.py -- <modello.glb> <tipo> [cartella_output] [--preview] [--only=<variante>]
    <tipo> = una chiave di KINDS (es. "mouse", "boss")

Output in assets/sprites/, per ogni variante v del tipo:
    enemy_<v>_<d>.png  enemy_<v>_walk_<d>.png  enemy_<v>_attack_<d>.png
I nomi delle varianti coincidono con Enemy.ENEMY_TYPE in game/enemy.py.
"""
import colorsys
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sprite_common as sc                                     # noqa: E402

WALK_FRAMES    = 8
ATTACK_SAMPLES = [0.12, 0.28, 0.42, 0.52, 0.64, 0.80]       # il frame 3 è il colpo

# Attacchi: (t, torsione°, braccio orizzontale°, braccio alzato°, braccio avanti/indietro°,
#            inclinazione busto°, slancio). Versi relativi al lato dell'arma:
#   torsione/braccio orizzontale + = arma verso dietro; braccio alzato + = in alto;
#   braccio avanti/indietro + = verso dietro e in alto; inclinazione + = busto in avanti
ATTACKS = {
    # fendente orizzontale: carica di lato, taglia di traverso davanti a sé
    "slash": [
        (0.00,   0,   0,   0,   0,   0,  0.00),
        (0.38,  28,  55,  25,   0,  -6, -0.03),
        (0.52, -22, -65,   5,   0,   6,  0.10),
        (0.68, -32, -95,  -5,   0,   5,  0.08),
        (1.00,   0,   0,   0,   0,   0,  0.00),
    ],
    # colpo dall'alto: arma sopra la testa, poi giù davanti con tutto il peso
    "smash": [
        (0.00,   0,   0,   0,   0,   0,  0.00),
        (0.38,  15,  20,  75,  50, -14, -0.04),
        (0.52, -10, -35, -10, -30,  26,  0.12),
        (0.68, -12, -40, -15, -40,  30,  0.12),
        (1.00,   0,   0,   0,   0,   0,  0.00),
    ],
}

# Ricolorazione del tessuto rosso (mantello/sciarpa): hue di arrivo in gradi
# (None = lascia il colore), moltiplicatori di saturazione e luminosità
KINDS = {
    "mouse": dict(
        hip=0.32, shoulder=0.56, neck=0.62, weapon_side=+1, arm_x=0.30, tail_y=0.35,
        leg_r=0.16, arm_r=0.12, attack="slash", res=72, ortho=2.15,
        variants={
            "mouse_warrior": (None, 1.0, 1.0),   # Ratto Guardia: rosso
            "mouse_archer":  (48,   1.0, 1.35),  # Ratto Esploratore: giallo
            "mouse_lancer":  (110,  0.9, 1.15),  # Ratto Lancia: verde
            "mouse_mage":    (255,  1.0, 1.25),  # Ratto Stregone: viola-blu
            "skeleton":      (210,  0.15, 1.5),  # Ratto Soldato: grigio acciaio
            "mouse_slinger": (28,   1.0, 1.3),   # Ratto Fromboliere: arancio
        },
        exposure=-0.9,                            # modello chiaro: luci tarate sul gatto nero
    ),
    "boss": dict(
        hip=0.38, shoulder=0.60, neck=0.62, weapon_side=-1, arm_x=0.35, tail_y=0.45,
        leg_r=0.18, arm_r=0.32, attack="smash", res=110, ortho=2.35, exposure=-0.6,
        variants={"boss": (None, 1.0, 1.0)},
    ),
}

ONLY = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--only=")]   # es. --only=mouse_slinger
sys.argv = [a for a in sys.argv if not a.startswith("--only=")]
(src, kind), out_dir, PREVIEW = sc.parse_args(2)
cfg = KINDS[kind]
ob, co, H = sc.load_model(Path(src))
x, y, z = co[:, 0], co[:, 1], co[:, 2]
smooth, V = sc.smooth, sc.V
S = cfg["weapon_side"]
hip_z, sh_z, neck_z = cfg["hip"] * H, cfg["shoulder"] * H, cfg["neck"] * H

# ── Rilevamento piedi, busto, braccia, coda ───────────────────────────────────
feet = co[z < 0.06 * H]
foot = {}
for side, name in ((-1, "R"), (1, "L")):          # guarda -Y: il lato destro è -X
    sel = feet[np.sign(feet[:, 0]) == side]
    foot[name] = (float(np.median(sel[:, 0])), float(np.median(sel[:, 1])))
torso  = co[(z > hip_z) & (z < neck_z) & (np.abs(x) < cfg["arm_x"])]
body_y = float(np.median(torso[:, 1]))
head   = co[z > neck_z + 0.1 * H]
head_y = float(np.median(head[:, 1]))


def arm_mask(side):
    return (smooth(cfg["arm_x"] - 0.06, cfg["arm_x"] + 0.06, side * x)
            * smooth(hip_z - 0.05 * H, hip_z + 0.05 * H, z)
            * smooth(sh_z + 0.14 * H, sh_z + 0.06 * H, z)
            * smooth(cfg["tail_y"], cfg["tail_y"] - 0.1, y))


arms = {}        # nome -> (spalla, estremità, linea spezzata spalla→gomito→mano→arma)
for side, name in ((-1, "R"), (1, "L")):
    pts = co[(arm_mask(side) > 0.5) & (y < body_y + 0.1)]     # davanti: niente mantello
    shoulder = np.array((side * cfg["arm_x"], float(np.median(pts[:, 1])) if len(pts) else body_y, sh_z))
    if len(pts) < 50:
        end = shoulder + (side * 0.3, 0, -0.2)
        arms[name] = (tuple(shoulder), tuple(end), [shoulder, end])
        continue
    # La linea segue il braccio piegato: baricentri di fasce di distanza dalla spalla
    dist = np.linalg.norm(pts - shoulder, axis=1)
    edges = np.linspace(0, dist.max(), 7)
    path = [shoulder] + [pts[(dist >= a) & (dist <= b)].mean(axis=0)
                         for a, b in zip(edges, edges[1:]) if ((dist >= a) & (dist <= b)).sum() > 5]
    path.append(pts[np.argmax(dist)])                          # punta della mano/arma
    arms[name] = (tuple(shoulder), tuple(path[-1]), path)
tail_pts = co[(y > cfg["tail_y"]) & (z > 0.05 * H)]
t_end    = tail_pts[np.argmax(np.hypot(tail_pts[:, 1] - body_y, tail_pts[:, 2] - hip_z))]
t0, t3   = V((0, cfg["tail_y"] - 0.05, hip_z)), V(tuple(t_end))
print("FEET", foot, "ARMS", {k: (np.round(a, 2), np.round(b, 2)) for k, (a, b, _) in arms.items()})

# ── Armatura ──────────────────────────────────────────────────────────────────
tail_chain = []
legs = {}
with sc.RigBuilder() as rb:
    rb.bone("hips",  (0, body_y, hip_z), (0, body_y, sh_z))
    rb.bone("chest", (0, body_y, sh_z), (0, head_y, neck_z), "hips")
    rb.bone("head",  (0, head_y, neck_z), (0, head_y, H), "chest")
    for name, (shoulder, hand, _) in arms.items():
        rb.bone(f"arm_{name}", shoulder, hand, "chest")
    for name, (fx, fy) in foot.items():
        hip  = V((fx * 0.55, (fy + body_y) / 2, hip_z))
        ft   = V((fx, fy, 0.03 * H))
        knee = hip.lerp(ft, 0.5)
        legs[name] = (hip, knee, ft)
        rb.bone(f"leg_{name}", hip, knee, "hips")
        rb.bone(f"shin_{name}", knee, ft, f"leg_{name}")
    prev = "hips"
    for i in range(3):
        prev = rb.bone(f"tail{i}", t0.lerp(t3, i / 3), t0.lerp(t3, (i + 1) / 3), prev)
        tail_chain.append(prev)
arm = rb.arm

# ── Pesi geometrici ───────────────────────────────────────────────────────────


def seg_dist(p, a, b):
    a, b = np.array(a), np.array(b)
    ab = b - a
    t  = np.clip(((p - a) @ ab) / (ab @ ab), 0, 1)
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1), t


n = len(co)
weights = {b.name: np.zeros(n) for b in arm.data.bones}
remaining = np.ones(n)
blend = 0.04 * H
for name, (hip, knee, ft) in legs.items():
    side = -1 if name == "R" else 1
    d1, _ = seg_dist(co, hip, knee)
    d2, _ = seg_dist(co, knee, ft)
    w = (smooth(cfg["leg_r"] * 1.2, cfg["leg_r"] * 0.8, np.minimum(d1, d2))
         * smooth(hip_z + blend, hip_z - blend, z)
         * smooth(-0.05, 0.05, side * x)) * remaining
    lower = smooth(knee.z + blend, knee.z - blend, z)
    weights[f"shin_{name}"] += w * lower
    weights[f"leg_{name}"]  += w * (1 - lower)
    remaining -= w
for name, (_, _, path) in arms.items():
    side = -1 if name == "R" else 1
    d = np.min([seg_dist(co, a, b)[0] for a, b in zip(path, path[1:])], axis=0)
    w = (smooth(cfg["arm_r"] * 1.3, cfg["arm_r"] * 0.8, d)
         * smooth(cfg["arm_x"] - 0.12, cfg["arm_x"] - 0.02, side * x)) * remaining
    weights[f"arm_{name}"] += w
    remaining -= w
tw = smooth(cfg["tail_y"] - 0.05, cfg["tail_y"] + 0.05, y) * remaining
_, tp = seg_dist(co, t0, t3)
for i, b in enumerate(tail_chain):
    weights[b] += tw * np.clip(1 - np.abs(tp * 3 - (i + 0.5)), 0, 1)
remaining -= tw
remaining = np.clip(remaining, 0, 1)
head_w  = smooth(neck_z - blend, neck_z + blend, z) * remaining
chest_w = smooth(hip_z + 0.05 * H, sh_z, z) * (remaining - head_w)
weights["head"]  += head_w
weights["chest"] += chest_w
weights["hips"]  += np.clip(remaining - head_w - chest_w, 0, 1)
sc.bind(ob, arm, weights)

scene = sc.SpriteScene(H, cfg["ortho"])
scene.sc.view_settings.exposure = cfg.get("exposure", 0.0)

# ── Pose ──────────────────────────────────────────────────────────────────────
X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)
weapon = "arm_L" if S > 0 else "arm_R"


def idle_pose():
    sc.reset_pose(arm)


def walk_pose(t: float):
    sc.reset_pose(arm)
    ph = 2 * math.pi * t
    for name, off in (("R", 0.0), ("L", math.pi)):
        a = ph + off
        sc.rotate(arm, f"leg_{name}", X, -28 * math.sin(a))          # - = gamba in avanti
        sc.rotate(arm, f"shin_{name}", X, 40 * max(0.0, math.cos(a)))  # ginocchio piegato in volo
        other = "L" if name == "R" else "R"
        swing = 6 if f"arm_{other}" == weapon else 16                 # braccio dell'arma più fermo
        sc.rotate(arm, f"arm_{other}", X, -swing * math.sin(a))       # braccia in controtempo
    sc.rotate(arm, "chest", Z, 5 * math.sin(ph))
    sc.rotate(arm, "head", X, 3 * math.sin(2 * ph))
    for i, b in enumerate(tail_chain):
        sc.rotate(arm, b, Z, 14 * math.sin(ph - i * 0.7))
    sc.offset_model(arm, up=0.02 * math.cos(2 * ph))


def attack_pose(t: float):
    sc.reset_pose(arm)
    twist, arm_z, raise_, arm_x, lean, lunge = sc.keyframes(ATTACKS[cfg["attack"]], t)
    sc.rotate(arm, "chest", Z, S * twist)
    sc.rotate(arm, "chest", X, lean)
    sc.rotate(arm, weapon, Z, S * arm_z)
    sc.rotate(arm, weapon, Y, -S * raise_)
    sc.rotate(arm, weapon, X, arm_x)
    for i, b in enumerate(tail_chain):
        sc.rotate(arm, b, Z, -S * twist * 0.4)
    sc.offset_model(arm, forward=lunge)


# ── Ricolorazione ─────────────────────────────────────────────────────────────
img  = sc.base_color_image(ob)
orig = np.empty(len(img.pixels), dtype=np.float32) if img else None
if img:
    img.pixels.foreach_get(orig)
    rgb = orig.reshape(-1, 4)[:, :3]
    mx, mn = rgb.max(axis=1), rgb.min(axis=1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    hue = 60 * (g - b) / np.maximum(mx - mn, 1e-6)          # gradi, valido dove r è il massimo
    # Tessuto rosso: tonalità rossa pura (il cuoio marrone sta sopra i 15°), saturo,
    # non troppo chiaro (esclude orecchie/coda rosa)
    cloth = (r >= g) & (r >= b) & (hue > -15) & (hue < 12) & (sat > 0.5) & (mx < 0.62)


def apply_variant(hue, sat_mul, val_mul):
    if not img:
        return
    px = orig.copy().reshape(-1, 4)
    if hue is not None or sat_mul != 1 or val_mul != 1:
        sel = px[cloth, :3]
        out = np.empty_like(sel)
        for i, (rr, gg, bb) in enumerate(sel):
            h, s_, v = colorsys.rgb_to_hsv(rr, gg, bb)
            out[i] = colorsys.hsv_to_rgb(hue / 360 if hue is not None else h,
                                         min(1, s_ * sat_mul), min(1, v * val_mul))
        px[cloth, :3] = out
    img.pixels.foreach_set(px.ravel())
    img.update()


if PREVIEW:
    first = next(iter(cfg["variants"].values()))
    apply_variant(*first)
    sc.render_preview(scene, arm, out_dir / f"preview_{kind}.png", walk_pose, WALK_FRAMES,
                      attack_pose, ATTACK_SAMPLES)
    if len(cfg["variants"]) > 1:                     # una posa per variante, per i colori
        tmp = out_dir / "_tmp_render.png"
        sc.face(arm, 1)
        idle_pose()
        frames = []
        for spec in cfg["variants"].values():
            apply_variant(*spec)
            frames.append(scene.render(tmp, sc.RENDER_RES))
        sc.save_png(out_dir / f"preview_{kind}_colors.png", np.concatenate(frames, axis=1))
        tmp.unlink(missing_ok=True)
    sys.exit(0)

for name, spec in cfg["variants"].items():
    if ONLY and name not in ONLY:
        continue
    apply_variant(*spec)
    sc.render_sprite_set(scene, arm, out_dir, f"enemy_{name}", cfg["res"],
                         idle_pose, walk_pose, WALK_FRAMES, attack_pose, ATTACK_SAMPLES)
    print(f"Variante {name} salvata")
print(f"Sprite salvati in {out_dir}")
