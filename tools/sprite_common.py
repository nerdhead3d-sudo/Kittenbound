"""Funzioni condivise dagli script Blender che generano gli sprite
(render_player_sprites.py, render_enemy_sprites.py).

Convenzioni: modello rivolto verso -Y, asse Z in alto (default degli export Meshy),
quindi il lato destro del personaggio è -X. Camera ortografica in vista 3/4 dall'alto.
Indice direzione d -> direzione su schermo d*45°: 0=E 1=SE 2=S 3=SW 4=W 5=NW 6=N 7=NE.
"""
import math
import time
import sys
from pathlib import Path

import bpy
import mathutils
import numpy as np

V = mathutils.Vector

RENDER_RES = 256                  # render ad alta risoluzione, poi ridimensionato

# --x2: sprite per la grafica HD (schermi 2560x1440). Stessa inquadratura, frame a doppia
# risoluzione salvati come <nome>@2x.png accanto a quelli normali.
SCALE = 2 if "--x2" in sys.argv else 1
if SCALE == 2:
    sys.argv.remove("--x2")
    RENDER_RES = 512
ELEVATION  = math.radians(55)     # inclinazione camera: vista 3/4 dall'alto
ORTHO_SIZE = 2.15                 # inquadratura (unità Blender), uguale per tutte le direzioni
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "sprites"


def parse_args(n_positional: int = 1):
    """Argomenti dopo '--': posizionali, [cartella_output], --preview."""
    argv    = sys.argv[sys.argv.index("--") + 1:]
    preview = "--preview" in argv
    argv    = [a for a in argv if a != "--preview"]
    pos     = argv[:n_positional]
    out_dir = Path(argv[n_positional]) if len(argv) > n_positional else ASSETS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    return pos, out_dir, preview


def smooth(edge0, edge1, v):
    """smoothstep vettoriale: 0 prima di edge0, 1 dopo edge1 (o il contrario se edge0 > edge1)."""
    t = np.clip((v - edge0) / (edge1 - edge0), 0, 1)
    return t * t * (3 - 2 * t)


# ── Modello ───────────────────────────────────────────────────────────────────

def load_model(src: Path):
    """Importa GLB/OBJ, unisce le mesh, centra in pianta con i piedi a z=0.
    Restituisce (oggetto, coordinate vertici Nx3, altezza)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if src.suffix.lower() in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(src))
    else:
        bpy.ops.wm.obj_import(filepath=str(src))

    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    bpy.ops.object.select_all(action='DESELECT')
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.parent = None
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    co = np.empty(len(ob.data.vertices) * 3)
    ob.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    co -= [(co[:, 0].min() + co[:, 0].max()) / 2, (co[:, 1].min() + co[:, 1].max()) / 2, co[:, 2].min()]
    ob.data.vertices.foreach_set("co", co.ravel())
    ob.data.update()

    # Materiale più opaco (gli export Meshy sono molto lucidi → effetto plastica)
    for mat in ob.data.materials:
        bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat and mat.use_nodes else None
        if bsdf:
            bsdf.inputs["Roughness"].default_value = 0.75
            bsdf.inputs["Specular IOR Level"].default_value = 0.2
    return ob, co, float(co[:, 2].max())


def base_color_image(ob):
    """Immagine collegata al Base Color del materiale (texture Meshy), o None."""
    for mat in ob.data.materials:
        bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat and mat.use_nodes else None
        if bsdf and bsdf.inputs["Base Color"].is_linked:
            node = bsdf.inputs["Base Color"].links[0].from_node
            if node.type == 'TEX_IMAGE':
                return node.image
    return None


# ── Armatura ──────────────────────────────────────────────────────────────────

class RigBuilder:
    """Crea le ossa in edit mode: with RigBuilder() as rb: rb.bone(...)."""

    def __enter__(self):
        arm_d = bpy.data.armatures.new("rig")
        self.arm = bpy.data.objects.new("rig", arm_d)
        bpy.context.scene.collection.objects.link(self.arm)
        bpy.context.view_layer.objects.active = self.arm
        bpy.ops.object.mode_set(mode='EDIT')
        self._eb = arm_d.edit_bones
        return self

    def bone(self, name, head, tail, parent=None):
        b = self._eb.new(name)
        b.head, b.tail = V(head), V(tail)
        b.roll = 0.0
        if parent:
            b.parent = self._eb[parent]
        return name

    def __exit__(self, *exc):
        bpy.ops.object.mode_set(mode='OBJECT')
        return False


def bind(ob, arm, weights: dict):
    """Normalizza i pesi {osso: array per vertice}, crea i vertex group e collega la mesh."""
    total = sum(weights.values())
    for name, w in weights.items():
        w = w / np.maximum(total, 1e-6)
        vg = ob.vertex_groups.new(name=name)
        rounded = np.round(w, 2)
        for val in np.unique(rounded[rounded > 0]):
            vg.add(np.nonzero(rounded == val)[0].tolist(), float(val), 'REPLACE')
    mod = ob.modifiers.new("rig", 'ARMATURE')
    mod.object = arm
    ob.parent = arm


def reset_pose(arm):
    for p in arm.pose.bones:
        p.rotation_mode = 'QUATERNION'
        p.rotation_quaternion = (1, 0, 0, 0)
        p.rotation_euler = (0, 0, 0)
        p.location = (0, 0, 0)
    arm.location = (0, 0, 0)


def rotate(arm, bone: str, axis, degrees: float):
    """Ruota un osso attorno a un asse espresso nello spazio del modello
    (X = sinistra del personaggio, -Y = avanti, Z = su), con perno nella testa dell'osso."""
    p = arm.pose.bones[bone]
    p.rotation_mode = 'QUATERNION'
    B = p.bone.matrix_local.to_quaternion()
    q = mathutils.Quaternion(V(axis), math.radians(degrees))
    p.rotation_quaternion = (B.inverted() @ q @ B) @ p.rotation_quaternion


def offset_model(arm, forward: float = 0.0, up: float = 0.0):
    """Sposta tutto il personaggio nello spazio del modello (avanti = -Y)."""
    arm.location = arm.matrix_world.to_3x3() @ V((0, -forward, up))


def keyframes(keys, t: float):
    """keys = [(t, v1, v2, ...), ...] crescenti in t → valori interpolati (ease in/out)."""
    for (t0, *a), (t1, *b) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            u = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            u = u * u * (3 - 2 * u)
            return [p + (q - p) * u for p, q in zip(a, b)]
    return list(keys[-1][1:])


# ── Scena di render ───────────────────────────────────────────────────────────

class SpriteScene:
    def __init__(self, height: float, ortho: float = ORTHO_SIZE):
        sc = self.sc = bpy.context.scene
        sc.render.engine = 'BLENDER_EEVEE'
        sc.render.film_transparent = True
        sc.render.resolution_x = sc.render.resolution_y = RENDER_RES
        sc.render.image_settings.file_format = 'PNG'
        sc.render.image_settings.color_mode  = 'RGBA'
        sc.view_settings.view_transform = 'Standard'

        world = bpy.data.worlds.new("world")
        sc.world = world
        world.use_nodes = True
        world.node_tree.nodes["Background"].inputs[0].default_value = (0.75, 0.78, 0.9, 1)
        world.node_tree.nodes["Background"].inputs[1].default_value = 1.6
        self._sun("key", 4.0, (45, 0, -30))                        # luce principale dall'alto-sinistra
        self._sun("rim", 3.0, (-60, 0, 20), (0.75, 0.85, 1.0))     # controluce per staccare la sagoma

        cam_d = bpy.data.cameras.new("cam")
        cam_d.type, cam_d.ortho_scale = 'ORTHO', ortho
        cam = bpy.data.objects.new("cam", cam_d)
        sc.collection.objects.link(cam)
        sc.camera = cam
        target = V((0, 0, height * 0.45))
        cam.location = target + V((0, -math.cos(ELEVATION), math.sin(ELEVATION))) * 6
        cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()

    def _sun(self, name, energy, rot_deg, color=(1, 1, 1)):
        ld = bpy.data.lights.new(name, 'SUN')
        ld.energy, ld.color = energy, color
        lo = bpy.data.objects.new(name, ld)
        lo.rotation_euler = [math.radians(a) for a in rot_deg]
        self.sc.collection.objects.link(lo)

    def render(self, tmp: Path, res: int) -> np.ndarray:
        res = min(res * SCALE, RENDER_RES) if res != RENDER_RES else res
        self.sc.render.filepath = str(tmp)
        for attempt in range(5):           # Windows a volte blocca il file per un attimo
            try:
                bpy.ops.render.render(write_still=True)
                break
            except RuntimeError:
                if attempt == 4:
                    raise
                time.sleep(0.5)
        img = bpy.data.images.load(str(tmp))
        if res != RENDER_RES:
            img.scale(res, res)
        px = np.empty(res * res * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        bpy.data.images.remove(img)
        return px.reshape(res, res, 4)


def face(arm, d: int, dirs: int = 8):
    """Orienta il personaggio verso la direzione schermo d su `dirs` (0 = est, senso orario;
    il modello guarda -Y = giù)."""
    arm.rotation_euler = (0, 0, math.radians(90 - d * 360 / dirs))
    bpy.context.view_layer.update()


def save_png(path: Path, pixels: np.ndarray):
    if SCALE == 2 and not path.stem.startswith("preview"):
        path = path.with_name(f"{path.stem}@2x{path.suffix}")
    h, w = pixels.shape[:2]
    img = bpy.data.images.new(path.stem, w, h, alpha=True)
    img.pixels.foreach_set(pixels.ravel())
    img.filepath_raw = str(path)
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)


def render_sprite_set(scene: SpriteScene, arm, out_dir: Path, prefix: str, res: int,
                      idle_pose, walk_pose, walk_frames: int, attack_pose, attack_samples):
    """Per ogni direzione: <prefix>_<d>.png (fermo), <prefix>_walk_<d>.png e
    <prefix>_attack_<d>.png (strip orizzontali)."""
    tmp = out_dir / "_tmp_render.png"
    for d in range(8):
        face(arm, d)
        idle_pose()
        save_png(out_dir / f"{prefix}_{d}.png", scene.render(tmp, res))
        frames = []
        for f in range(walk_frames):
            walk_pose(f / walk_frames)
            frames.append(scene.render(tmp, res))
        save_png(out_dir / f"{prefix}_walk_{d}.png", np.concatenate(frames, axis=1))
        frames = []
        for t in attack_samples:
            attack_pose(t)
            frames.append(scene.render(tmp, res))
        save_png(out_dir / f"{prefix}_attack_{d}.png", np.concatenate(frames, axis=1))
    tmp.unlink(missing_ok=True)


def render_preview(scene: SpriteScene, arm, path: Path, walk_pose, walk_frames: int,
                   attack_pose, attack_samples, dirs=(0, 1, 2)):
    """Anteprima ad alta risoluzione: una riga per direzione, metà camminata + attacco."""
    tmp = path.parent / "_tmp_render.png"
    rows = []
    for d in dirs:
        face(arm, d)
        frames = []
        for f in range(0, walk_frames, 2):
            walk_pose(f / walk_frames)
            frames.append(scene.render(tmp, RENDER_RES))
        for t in attack_samples:
            attack_pose(t)
            frames.append(scene.render(tmp, RENDER_RES))
        rows.append(np.concatenate(frames, axis=1))
    save_png(path, np.concatenate(rows[::-1], axis=0))     # pixel Blender: dal basso
    tmp.unlink(missing_ok=True)
    print(f"Anteprima salvata in {path}")
