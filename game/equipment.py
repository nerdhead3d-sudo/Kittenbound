"""Equipaggiamento del gatto: 3 slot (artigli, collare, amuleto) e uno zaino.

È l'unica cosa che resta anche morendo, per questo è raro: lo lasciano i boss (sempre), i
forzieri delle stanze speciali (di rado) e il mercante nascosto (caro). Gli oggetti con un
bonus di statistiche lo applicano quando li indossi e lo tolgono quando li togli; gli altri
hanno un effetto che il gioco controlla con has(player, id).
"""
import math
import random

import pygame

from game import settings as s
from game.sound import play

SLOTS      = ("claws", "collar", "amulet")
SLOT_NAMES = {"claws": "Artigli", "collar": "Collare", "amulet": "Amuleto"}
RARITY_NAMES  = {1: "Comune", 2: "Raro", 3: "Leggendario"}
RARITY_COLORS = {1: (196, 200, 210), 2: (110, 170, 255), 3: (255, 176, 70)}
BACKPACK_SIZE = 9


class Item:
    def __init__(self, name, slot, rarity, desc, color, stats=None):
        self.name, self.slot, self.rarity, self.desc = name, slot, rarity, desc
        self.color = color
        self.stats = stats or {}          # attributo del gatto -> bonus (applicato indossandolo)


ITEMS = {
    # Artigli
    "claws_sharp":    Item("Artigli Affilati", "claws", 1, "+6 danno degli attacchi",
                           (200, 205, 215), {"melee_damage_bonus": 6}),
    "claws_serrated": Item("Unghie Seghettate", "claws", 2,
                           f"I colpi fanno sanguinare: {s.BLEED_DPS} danni al secondo per {s.BLEED_TIME:g} s",
                           (220, 70, 80)),
    "claws_obsidian": Item("Artigli d'Ossidiana", "claws", 3,
                           "Il critico della schivata perfetta esplode e colpisce tutti i nemici vicini",
                           (150, 90, 230)),
    # Collari
    "collar_leather": Item("Collare di Cuoio", "collar", 1, "+25 vita massima",
                           (170, 110, 60), {"hp_max": 25}),
    "collar_stray":   Item("Collare del Randagio", "collar", 2,
                           "Nell'acqua non rallenti e corri l'8% più veloce",
                           (80, 190, 150), {"speed_bonus": 0.08}),
    "collar_bell":    Item("Campanellino d'Argento", "collar", 3,
                           f"{round(s.BELL_EVADE * 100)}% di probabilità di evitare un colpo",
                           (230, 230, 245)),
    # Amuleti
    "amulet_moon":    Item("Pietra Lunare", "amulet", 1, "+25 energia massima, +1 energia al secondo",
                           (150, 190, 255), {"energy_max": 25, "energy_regen_bonus": 1.0}),
    "amulet_cateye":  Item("Occhio di Gatto", "amulet", 2,
                           "Vedi i nemici anche al buio, e il buio è meno fitto",
                           (120, 230, 90)),
    "amulet_flame":   Item("Fiamma Audace", "amulet", 3, "L'Audacia sale il doppio",
                           (255, 120, 50)),
}


# ── Stato sul gatto ───────────────────────────────────────────────────────────

def has(player, item_id: str) -> bool:
    return item_id in getattr(player, "equipment", {}).values()


def owns(player, item_id: str) -> bool:
    return has(player, item_id) or item_id in getattr(player, "backpack", [])


def _apply_stats(player, item_id: str, sign: int):
    for attr, bonus in ITEMS[item_id].stats.items():
        setattr(player, attr, getattr(player, attr) + sign * bonus)
        if attr == "hp_max":
            player.hp = max(1.0, min(float(player.hp_max), player.hp + sign * bonus))
        elif attr == "energy_max":
            player.energy = max(0.0, min(float(player.energy_max), player.energy + sign * bonus))


def equip(player, item_id: str):
    """Indossa un oggetto dello zaino; quello che c'era nello slot torna nello zaino."""
    item = ITEMS[item_id]
    if item_id in player.backpack:
        player.backpack.remove(item_id)
    old = player.equipment.get(item.slot)
    if old:
        _apply_stats(player, old, -1)
        player.backpack.append(old)
    player.equipment[item.slot] = item_id
    _apply_stats(player, item_id, +1)


def unequip(player, slot: str) -> bool:
    old = player.equipment.get(slot)
    if not old or len(player.backpack) >= BACKPACK_SIZE:
        return False
    _apply_stats(player, old, -1)
    player.equipment[slot] = None
    player.backpack.append(old)
    return True


def give(player, item_id: str, announce: bool = True) -> bool:
    """Nuovo oggetto: lo indossa se lo slot è libero, altrimenti va nello zaino."""
    if owns(player, item_id) or item_id not in ITEMS:
        return False
    item = ITEMS[item_id]
    if player.equipment.get(item.slot) is None:
        player.equipment[item.slot] = item_id
        _apply_stats(player, item_id, +1)
    elif len(player.backpack) < BACKPACK_SIZE:
        player.backpack.append(item_id)
    else:
        return False
    if announce:
        player.say(f"{RARITY_NAMES[item.rarity]}: {item.name}  (I per vederlo)", RARITY_COLORS[item.rarity], 3.0)
        play("level_up", 0.8)
    return True


def roll(player, weights: dict, rng=random) -> "str | None":
    """Un oggetto che il gatto non ha ancora, con le rarità pesate come in `weights`."""
    pool = [i for i in ITEMS if not owns(player, i) and weights.get(ITEMS[i].rarity, 0) > 0]
    if not pool:
        return None
    return rng.choices(pool, [weights[ITEMS[i].rarity] for i in pool])[0]


def snapshot(player) -> dict:
    return {"equipment": dict(player.equipment), "backpack": list(player.backpack)}


def restore(player, gear: "dict | None"):
    """Rimette l'equipaggiamento (es. al gatto nuovo dopo una morte), con i suoi bonus."""
    if not gear:
        return
    player.backpack = [i for i in gear.get("backpack", []) if i in ITEMS]
    for slot, item_id in (gear.get("equipment") or {}).items():
        if item_id in ITEMS and slot in player.equipment:
            player.equipment[slot] = item_id
            _apply_stats(player, item_id, +1)


# ── Icone ─────────────────────────────────────────────────────────────────────
#
# Quelle dipinte (assets/sprites/icons/<id>.png, tagliate con tools/slice_icons.py);
# se manca il file, una disegnata qui sotto.

_icon_cache: dict = {}


def icon(name: str, size: int):
    """Icona dipinta (oggetto, o "spell_<id>" per le magie) alla dimensione logica `size`."""
    key = (name, size)
    if key not in _icon_cache:
        from game import gfx
        from game.asset_manager import AssetManager
        path = AssetManager.image_path(f"icons/{name}")
        _icon_cache[key] = (gfx.fit(pygame.image.load(str(path)).convert_alpha(), (size, size))
                            if path.exists() else None)
    return _icon_cache[key]

def _shade(c, d):
    return tuple(max(0, min(255, v + d)) for v in c)


def draw_icon(surface, item_id: str, center, size: int):
    img = icon(item_id, size)
    if img is not None:
        surface.blit(img, img.get_rect(center=center))
        return
    item = ITEMS[item_id]
    cx, cy = center
    col, dark, light = item.color, _shade(item.color, -70), _shade(item.color, 60)
    r = size // 2
    if item.slot == "claws":                     # tre artigli ricurvi
        for k in (-1, 0, 1):
            bx = cx + k * r * 0.42
            pts = [(bx - r * 0.13, cy + r * 0.55), (bx + r * 0.13, cy + r * 0.55),
                   (bx + r * 0.16 + k * r * 0.06, cy - r * 0.15), (bx + r * 0.02 + k * r * 0.2, cy - r * 0.72)]
            pygame.draw.polygon(surface, dark, [(x + 2, y + 2) for x, y in pts])
            pygame.draw.polygon(surface, col, pts)
            pygame.draw.line(surface, light, pts[0], pts[3], 2)
        pygame.draw.rect(surface, _shade(col, -40), (cx - r * 0.6, cy + r * 0.5, r * 1.2, r * 0.3), border_radius=4)
    elif item.slot == "collar":                  # collare con la medaglietta
        rect = pygame.Rect(0, 0, round(r * 1.7), round(r * 1.1))
        rect.center = (cx, cy - round(r * 0.15))
        pygame.draw.ellipse(surface, dark, rect.move(2, 2), max(4, r // 4))
        pygame.draw.ellipse(surface, col, rect, max(4, r // 4))
        pygame.draw.arc(surface, light, rect.inflate(-4, -4), math.pi * 1.1, math.pi * 1.6, 2)
        pygame.draw.circle(surface, (225, 190, 70), (cx, cy + round(r * 0.48)), max(4, r // 4))
        pygame.draw.circle(surface, (255, 235, 150), (cx - 2, cy + round(r * 0.44)), max(1, r // 10))
    else:                                        # amuleto: gemma con la catenina
        pygame.draw.arc(surface, (200, 190, 150), (cx - r * 0.7, cy - r * 1.0, r * 1.4, r * 1.1), 0, math.pi, 2)
        gem = [(cx, cy - r * 0.45), (cx + r * 0.5, cy + r * 0.05), (cx, cy + r * 0.7), (cx - r * 0.5, cy + r * 0.05)]
        pygame.draw.polygon(surface, dark, [(x + 2, y + 2) for x, y in gem])
        pygame.draw.polygon(surface, col, gem)
        pygame.draw.polygon(surface, light, [gem[0], gem[1], (cx, cy + r * 0.05), gem[3]])
        pygame.draw.circle(surface, (255, 255, 255), (round(cx - r * 0.15), round(cy - r * 0.1)), max(1, r // 9))
