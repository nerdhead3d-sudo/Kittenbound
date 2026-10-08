"""Genera gli sprite del player da un modello 3D di gatto con Blender:
scheletro automatico da quadrupede + camminata + graffio, 8 direzioni, vista 3/4 dall'alto.

Uso (da terminale, nella root del progetto):
    blender -b --python tools/render_player_sprites.py -- <modello.glb|.obj> [cartella_output] [--preview]
        [--idle] [--prefix=NOME] [--res=PX] [--dirs=N]

--idle: gatti fermi (NPC dell'hub): invece di camminata e graffio genera <prefix>_idle_<d>.png,
un ciclo da fermo (respiro, testa che si guarda attorno, coda che ondeggia), in --dirs direzioni
(default 32: l'NPC si gira in modo fluido verso il giocatore).

Output in assets/sprites/:
    player_<d>.png         posa ferma per direzione d (+ player.png = direzione S)
    player_walk_<d>.png    strip orizzontale di WALK_FRAMES frame
    player_attack_<d>.png  strip orizzontale del graffio (ATTACK_SAMPLES)
Il modello deve guardare verso -Y con l'asse Z verso l'alto (default degli export Meshy)
e stare in piedi su quattro zampe separate sotto la pancia.
"""
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sprite_common as sc                                     # noqa: E402

OPTS = {k: v for k, _, v in (a[2:].partition("=") for a in sys.argv
                               if a.startswith("--") and a not in ("--", "--preview"))}
sys.argv = [a for a in sys.argv if not (a.startswith("--") and a[2:].partition("=")[0] in OPTS)]

PREFIX      = OPTS.get("prefix", "player")
IDLE_ONLY   = "idle" in OPTS
SPRITE_RES  = int(OPTS.get("res", 72))   # dimensione finale di ogni frame (px)
WALK_FRAMES = 8
IDLE_FRAMES = 12
IDLE_DIRS   = int(OPTS.get("dirs", 32))
HEAD_UP     = 16                   # NPC: testa alzata (gradi) per mostrare il muso sotto il cappello

# Proporzioni del rig, in frazioni dell'altezza del modello (piedi = 0, testa = 1)
BELLY_FRAC = 0.30                  # attacco delle zampe al corpo
KNEE_FRAC  = 0.15                  # ginocchio / garretto
SHOULDER_FRAC = 0.12               # le zampe anteriori partono più in alto (spalla) per poter graffiare
FOOT_FRAC  = 0.10                  # fetta usata per trovare le zampe

# Ampiezze del ciclo di camminata
LEG_SWING  = math.radians(28)
KNEE_BEND  = math.radians(35)
TAIL_SWAY  = math.radians(12)
HEAD_NOD   = math.radians(3)
BODY_BOB   = 0.015

# Attacco con artigli: frame campionati lungo la curva ATTACK_KEYS
ATTACK_SAMPLES = [0.12, 0.28, 0.42, 0.52, 0.64, 0.80]
#   impennata: + = muso in alto     slancio: + = corpo in avanti
#   alzata: + = zampa in avanti/su  graffio: + = verso l'esterno, - = di traverso davanti al muso
#   gomito: + = zampa raccolta all'indietro
#   t     impennata°  slancio  alzata°  graffio°  gomito°  testa°
ATTACK_KEYS = [
    (0.00,   0,        0.00,     0,       0,        0,       0),
    (0.35,  22,       -0.05,   120,      35,       60,      -8),   # caricamento
    (0.52,  -6,        0.10,    85,     -40,      -10,       8),   # colpo
    (0.68,  -8,        0.08,    55,     -65,       20,       5),   # accompagnamento
    (1.00,   0,        0.00,     0,       0,        0,       0),   # ritorno
]

# Versi delle rotazioni rispetto agli assi locali delle ossa (verificati con --preview)
SIGN_PITCH  = -1
SIGN_SWING  = 1
SIGN_KNEE_F = -1
SIGN_SWIPE  = -1

(src,), out_dir, PREVIEW = sc.parse_args(1)
ob, co, H = sc.load_model(Path(src))
x, y, z = co[:, 0], co[:, 1], co[:, 2]
V = sc.V

# ── Rilevamento zampe ─────────────────────────────────────────────────────────
belly_z, knee_z = H * BELLY_FRAC, H * KNEE_FRAC
feet  = co[z < H * FOOT_FRAC]
y_mid = (feet[:, 1].min() + feet[:, 1].max()) / 2      # separa zampe anteriori (y<) e posteriori
legs = {}
# Il gatto guarda -Y: il suo lato destro è -X
for name, fx, fy in (("FR", -1, -1), ("FL", 1, -1), ("BR", -1, 1), ("BL", 1, 1)):
    sel = feet[(np.sign(feet[:, 0]) == fx) & (np.sign(feet[:, 1] - y_mid) == fy)]
    legs[name] = (float(np.median(sel[:, 0])), float(np.median(sel[:, 1])))
leg_r = 0.6 * min(abs(legs["FL"][0] - legs["FR"][0]), abs(legs["FL"][1] - legs["BL"][1]))
front_y = (legs["FL"][1] + legs["FR"][1]) / 2
back_y  = (legs["BL"][1] + legs["BR"][1]) / 2
print("LEGS", {k: (round(a, 3), round(b, 3)) for k, (a, b) in legs.items()}, "r", round(leg_r, 3))

# ── Armatura ──────────────────────────────────────────────────────────────────
tail_root_y = co[:, 1].max() * 0.35                      # inizio coda: dietro le zampe posteriori
tail_pts = co[(y > tail_root_y) & (z > belly_z)]
t_end = tail_pts[np.argmax(tail_pts[:, 1] * 0.5 + tail_pts[:, 2])] if len(tail_pts) else (0, tail_root_y + 0.4, H * 0.8)
t0 = V((0, tail_root_y, belly_z + 0.15 * H))
t3 = V((0, float(t_end[1]), float(t_end[2])))
tail_chain = []
with sc.RigBuilder() as rb:
    rb.bone("body", (0, back_y, belly_z + 0.15 * H), (0, front_y, belly_z + 0.18 * H))
    rb.bone("head", (0, front_y, belly_z + 0.25 * H), (0, front_y - 0.05, H), "body")
    prev = "body"
    for i in range(3):
        prev = rb.bone(f"tail{i}", t0.lerp(t3, i / 3), t0.lerp(t3, (i + 1) / 3), prev)
        tail_chain.append(prev)
    for name, (lx, ly) in legs.items():
        top = belly_z + (SHOULDER_FRAC * H if name[0] == "F" else 0.0)
        rb.bone(f"{name}_up", (lx, ly, top), (lx, ly, knee_z), "body")
        rb.bone(f"{name}_lo", (lx, ly, knee_z), (lx, ly, 0.0), f"{name}_up")
arm = rb.arm

# ── Pesi geometrici ───────────────────────────────────────────────────────────
n = len(co)
weights = {b.name: np.zeros(n) for b in arm.data.bones}
smooth = sc.smooth
blend = 0.04 * H
remaining = np.ones(n)
for name, (lx, ly) in legs.items():
    d_xy   = np.hypot(x - lx, y - ly)
    if name[0] == "F":   # spalla: passaggio graduale dal corpo alla zampa
        vert = smooth(belly_z + SHOULDER_FRAC * H, belly_z - blend, z)
    else:
        vert = smooth(belly_z + blend, belly_z - blend, z)
    in_leg = smooth(leg_r * 1.15, leg_r * 0.85, d_xy) * vert
    lower  = smooth(knee_z + blend, knee_z - blend, z)
    weights[f"{name}_lo"] += in_leg * lower
    weights[f"{name}_up"] += in_leg * (1 - lower)
    remaining -= in_leg
remaining = np.clip(remaining, 0, 1)

# Coda: lungo la catena, con passaggio morbido dal corpo
seg_len = (t3 - t0).length
tail_w  = smooth(tail_root_y - 0.05, tail_root_y + 0.05, y) * smooth(belly_z - blend, belly_z + blend, z) * remaining
tdir    = np.array((t3 - t0).normalized())
proj    = np.clip(((co - np.array(t0)) @ tdir) / seg_len, 0, 0.999)
for i, b in enumerate(tail_chain):
    weights[b] += tail_w * np.clip(1 - np.abs(proj * 3 - (i + 0.5)), 0, 1)
remaining -= tail_w

# Testa: davanti e sopra il collo
if IDLE_ONLY:   # NPC con cappello: tutto ciò che sta sopra il collo (cappello compreso) segue la testa
    head_w = smooth(0.30, 0.20, y) * smooth(0.50 * H, 0.58 * H, z) * remaining
else:
    head_w = smooth(front_y + 0.25, front_y + 0.1, y) * smooth(belly_z + 0.2 * H, belly_z + 0.3 * H, z) * remaining
weights["head"] += head_w
weights["body"] += np.clip(remaining - head_w, 0, 1)
sc.bind(ob, arm, weights)

scene = sc.SpriteScene(H)

# ── Pose ──────────────────────────────────────────────────────────────────────
pb = arm.pose.bones


def reset_pose():
    for p in pb:
        p.rotation_mode = 'XYZ'
        p.rotation_euler = (0, 0, 0)
        p.location = (0, 0, 0)


def set_walk_pose(t: float | None):
    """t in [0,1) = fase della camminata; None = posa ferma."""
    reset_pose()
    if t is None:
        return
    ph = 2 * math.pi * t
    # Trotto: zampe diagonali in coppia
    for name, off in (("FL", 0), ("BR", 0), ("FR", math.pi), ("BL", math.pi)):
        a = ph + off
        pb[f"{name}_up"].rotation_euler.x = LEG_SWING * math.sin(a)
        lift = max(0.0, math.cos(a))                       # fase di volo: zampa che avanza
        bend = KNEE_BEND * lift
        pb[f"{name}_lo"].rotation_euler.x = -bend if name[0] == "F" else bend
    pb["body"].location.z = BODY_BOB * math.cos(2 * ph)   # su e giù due volte per ciclo
    pb["head"].rotation_euler.x = HEAD_NOD * math.sin(2 * ph)
    for i, b in enumerate(tail_chain):
        pb[b].rotation_euler.z = TAIL_SWAY * math.sin(ph - i * 0.6)


def set_attack_pose(t: float):
    """t in [0,1]: graffio con la zampa anteriore destra.
    Caricamento (si impenna, zampa alzata) → colpo (slancio + graffio di traverso)
    → accompagnamento → ritorno."""
    reset_pose()
    pitch, lunge, raise_, swipe, bend, head = sc.keyframes(ATTACK_KEYS, t)
    rad = math.radians
    pb["body"].rotation_euler.x = SIGN_PITCH * rad(pitch)
    pb["body"].location.y       = lunge
    for hind in ("BL", "BR"):                               # zampe posteriori restano piantate
        pb[f"{hind}_up"].rotation_euler.x = -SIGN_PITCH * rad(pitch)
    pb["FR_up"].rotation_euler.x = SIGN_SWING * rad(raise_)
    pb["FR_up"].rotation_euler.y = SIGN_SWIPE * rad(swipe)   # zampa alzata: ruota attorno alla verticale
    pb["FR_lo"].rotation_euler.x = SIGN_KNEE_F * rad(bend)
    pb["FL_up"].rotation_euler.x = SIGN_SWING * rad(raise_ * 0.35)   # l'altra zampa si raccoglie
    pb["FL_lo"].rotation_euler.x = SIGN_KNEE_F * rad(bend * 0.6)
    pb["head"].rotation_euler.x  = SIGN_PITCH * rad(head)
    for i, b in enumerate(tail_chain):
        pb[b].rotation_euler.x = SIGN_PITCH * rad(pitch * 0.5)


def set_idle_pose(t: float):
    """t in [0,1): ciclo da fermo. Respira, gira un po' la testa, muove la coda."""
    reset_pose()
    ph = 2 * math.pi * t
    pb["body"].location.z = 0.006 * math.sin(2 * ph)
    pb["head"].rotation_euler.x = SIGN_PITCH * math.radians(HEAD_UP + 2.5 * math.sin(2 * ph + 0.6))
    pb["head"].rotation_euler.z = math.radians(5) * math.sin(ph)
    for i, b in enumerate(tail_chain):
        pb[b].rotation_euler.z = math.radians(16) * math.sin(ph - i * 0.7)
        pb[b].rotation_euler.x = SIGN_PITCH * math.radians(4) * math.sin(2 * ph - i * 0.5)


if IDLE_ONLY:
    tmp = out_dir / "_tmp_render.png"
    dirs = (0, IDLE_DIRS // 8, IDLE_DIRS // 4) if PREVIEW else range(IDLE_DIRS)
    rows = []
    for d in dirs:
        sc.face(arm, d, IDLE_DIRS)
        frames = []
        for f in range(IDLE_FRAMES):
            set_idle_pose(f / IDLE_FRAMES)
            frames.append(scene.render(tmp, sc.RENDER_RES if PREVIEW else SPRITE_RES))
        if PREVIEW:
            rows.append(np.concatenate(frames[::3], axis=1))
        else:
            sc.save_png(out_dir / f"{PREFIX}_idle_{d}.png", np.concatenate(frames, axis=1))
    if PREVIEW:
        sc.save_png(out_dir / "preview.png", np.concatenate(rows[::-1], axis=0))
    else:
        # Punto d'appoggio a terra: px sotto il centro del frame (la camera inquadra 0.45 H).
        # Uguale in tutte le direzioni: il gioco lo usa per poggiare i piedi sull'ombra.
        ground = 0.45 * H * math.cos(sc.ELEVATION) * SPRITE_RES / sc.ORTHO_SIZE
        (out_dir / f"{PREFIX}_meta.json").write_text(json.dumps({"ground_px": round(ground, 2)}))
    tmp.unlink(missing_ok=True)
    print(f"Sprite salvati in {out_dir}")
    sys.exit(0)

if PREVIEW:
    sc.render_preview(scene, arm, out_dir / "preview.png", set_walk_pose, WALK_FRAMES,
                      set_attack_pose, ATTACK_SAMPLES)
    sys.exit(0)

sc.render_sprite_set(scene, arm, out_dir, "player", SPRITE_RES,
                     lambda: set_walk_pose(None), set_walk_pose, WALK_FRAMES,
                     set_attack_pose, ATTACK_SAMPLES)
x2 = "@2x" if sc.SCALE == 2 else ""
shutil.copy(out_dir / f"player_2{x2}.png", out_dir / f"player{x2}.png")
print(f"Sprite salvati in {out_dir}")
