# ─── Window ───────────────────────────────────────────────────────────────────
SCREEN_W = 1280
SCREEN_H = 720
FPS = 60
TITLE = "Kittenbound"

# ─── Tile & Room ──────────────────────────────────────────────────────────────
TILE_SIZE = 48
ROOM_COLS = 20
ROOM_ROWS = 14

# ─── Dungeon ──────────────────────────────────────────────────────────────────
DUNGEON_ROOMS = 8
DUNGEON_COLS = 5
DUNGEON_ROWS = 4

# ─── Player ───────────────────────────────────────────────────────────────────
PLAYER_SPEED              = 220
PLAYER_HP_MAX             = 100
PLAYER_ENERGY_MAX         = 100
PLAYER_RADIUS             = 16
PLAYER_INVINCIBILITY_TIME = 0.30
PLAYER_ENERGY_REGEN       = 5.0     # EN/s
PLAYER_HP_REGEN           = 1.5

# ─── Energy costs ─────────────────────────────────────────────────────────────
PLAYER_ENERGY_MELEE_COST  = 8
PLAYER_ENERGY_DODGE_COST  = 12
PLAYER_ENERGY_SPELL_COST  = 25

# ─── Leveling ─────────────────────────────────────────────────────────────────
XP_PER_LEVEL           = [0, 50, 120, 220, 360, 550]
HP_BONUS_PER_LEVEL     = 15
ENERGY_BONUS_PER_LEVEL = 10

# ─── Spell ────────────────────────────────────────────────────────────────────
SPELL_FIREBALL_SPEED  = 380
SPELL_FIREBALL_RADIUS = 8
SPELL_SHOT_SPEED      = 480
SPELL_SHOT_DAMAGE     = 15
SPELL_MARK_DURATION   = 1.5
SPELL_CLAW_DAMAGE     = 65
SPELL_SHOT_COOLDOWN   = 8.0

# ─── Melee combat ─────────────────────────────────────────────────────────────
PLAYER_MELEE_DAMAGE   = 35
PLAYER_MELEE_RANGE    = 70
PLAYER_MELEE_COOLDOWN = 0.30
PLAYER_MELEE_ACTIVE   = 0.12

# ─── Animazioni player (sprite in assets/sprites/) ────────────────────────────
PLAYER_WALK_FPS        = 12
# Durata di ogni frame del graffio: caricamento rapido, colpo e accompagnamento più lunghi
PLAYER_ATTACK_FRAME_T  = (0.03, 0.03, 0.04, 0.06, 0.06, 0.06)
PLAYER_ATTACK_STRIKE   = 3      # frame del colpo: da qui compaiono i graffi

# ─── Animazioni nemici ────────────────────────────────────────────────────────
ENEMY_HITBOX_SIZE      = 36     # hitbox fissa, indipendente dalla dimensione dello sprite
ENEMY_ATTACK_STRIKE    = 3      # frame del colpo nella strip d'attacco (prima: caricamento)
ENEMY_ATTACK_RECOVER   = 0.20   # s di animazione dopo il colpo (accompagnamento + ritorno)

# ─── Dodge roll ───────────────────────────────────────────────────────────────
PLAYER_DODGE_SPEED    = 300
PLAYER_DODGE_DURATION = 0.20
PLAYER_DODGE_PERFECT  = 0.09
PLAYER_DODGE_COOLDOWN = 0.65

# ─── Enemy ────────────────────────────────────────────────────────────────────
ENEMY_CHASE_RANGE      = 320
ENEMY_ATTACK_RANGE     = 60
ENEMY_ATTACK_COOLDOWN  = 1.2
ENEMY_WINDUP_TIME      = 0.30
ENEMY_PROJECTILE_SPEED = 260
ENEMY_PROJECTILE_RANGE = 400

# ─── Loot ─────────────────────────────────────────────────────────────────────
COIN_VALUE          = 5
POTION_HP_VALUE     = 30
POTION_ENERGY_VALUE = 25
LOOT_RADIUS         = 10
GOLD_DROP_MIN       = 2
GOLD_DROP_MAX       = 10
CHEST_OPEN_RADIUS   = 50

# ─── Colors (palette fiabesca) ────────────────────────────────────────────────
C_FLOOR       = (90,  80,  70)
C_FLOOR_ALT   = (80,  72,  62)
C_WALL        = (55,  52,  60)
C_WALL_LIT    = (70,  67,  78)

# ─── Finto 3D (2.5D) ──────────────────────────────────────────────────────────
WALL_HEIGHT     = 30                # altezza visiva dei muri (px): faccia frontale
C_WALL_TOP      = (82,  77,  92)    # cima dei muri
C_WALL_FACE     = (52,  47,  58)    # faccia frontale (mattoni)
C_WALL_MORTAR   = (34,  31,  40)
SHADOW_ALPHA    = 95                # ombre a terra di personaggi e oggetti
AO_ALPHA        = 120               # ombra alla base dei muri sul pavimento
LIGHT_RADIUS    = 330               # alone di luce attorno al gatto
DARKNESS_ALPHA  = 120               # buio massimo lontano dal gatto

C_PLAYER      = (30,  28,  35)
C_PLAYER_ROBE = (40,  90,  55)
C_PLAYER_EYE  = (80, 220,  90)

C_MOUSE_WARRIOR = (160,  50,  50)
C_MOUSE_ARCHER  = (180, 150,  40)
C_MOUSE_MAGE    = ( 80,  80, 200)
C_MOUSE_LANCER  = ( 70, 150,  60)
C_SKELETON      = (210, 210, 190)

C_PROJ_PLAYER   = ( 80, 220, 130)
C_PROJ_ENEMY    = (220,  80,  60)

C_COIN          = (240, 200,  50)
C_POTION_HP     = (220,  60,  60)
C_POTION_ENERGY = ( 60, 120, 220)

C_HP_BAR     = (200,  50,  50)
C_ENERGY_BAR = (240, 200,  50)
C_XP_BAR     = ( 80, 200,  90)
C_BAR_BG     = ( 30,  30,  35)
C_TEXT       = (230, 225, 220)
C_DOOR_OPEN  = (120, 200, 130)

# ─── Biomi ────────────────────────────────────────────────────────────────────
BOSCO_FLOORS = 4

# ─── Game states ──────────────────────────────────────────────────────────────
STATE_PLAYING         = "playing"
STATE_DEAD            = "dead"
STATE_PAUSE           = "pause"
STATE_HUB             = "hub"
STATE_VENDOR          = "vendor"
STATE_DUNGEON_CONFIRM = "dungeon_confirm"
STATE_FLOOR_COMPLETE  = "floor_complete"

# ─── Hub ──────────────────────────────────────────────────────────────────────
VENDOR_INTERACT_RADIUS   = 80
ENTRANCE_INTERACT_RADIUS = 80

# ─── Room types ───────────────────────────────────────────────────────────────
ROOM_TYPE_NORMAL    = "normal"
ROOM_TYPE_SPECIAL   = "special"
ROOM_TYPE_BOSS      = "boss"
ROOM_TYPE_START     = "start"
SPECIAL_ROOMS_COUNT = 2

# ─── Boss room arena ──────────────────────────────────────────────────────────
BOSS_ROOM_COLS = 16
BOSS_ROOM_ROWS = 11

# ─── Boss: Topo Armaturato ────────────────────────────────────────────────────
BOSS_HP                 = 450
BOSS_DAMAGE_MELEE       = 18
BOSS_DAMAGE_CHARGE      = 30
BOSS_SPEED_PATROL       = 80
BOSS_CHARGE_SPEED       = 480
BOSS_WINDUP_TIME        = 1.2
BOSS_WINDUP_RAGE_TIME   = 0.7
BOSS_STUN_DURATION      = 2.0
BOSS_STUN_RAGE_DURATION = 1.2
BOSS_RAGE_THRESHOLD     = 0.30
BOSS_FEINT_CHANCE       = 0.45

# Colpo Spazzante
BOSS_SWEEP_DAMAGE   = 28
BOSS_SWEEP_WINDUP   = 1.0
BOSS_SWEEP_RANGE    = 90
BOSS_SWEEP_ACTIVE   = 0.15
BOSS_SWEEP_COOLDOWN = 5.0

# Codata
BOSS_PROXIMITY_TIME  = 2.5
BOSS_PROXIMITY_RANGE = 55
BOSS_TAIL_DAMAGE     = 12
BOSS_TAIL_RANGE      = 80
BOSS_TAIL_STUN       = 1.5
BOSS_TAIL_DURATION   = 0.40

# ─── Ratto Esploratore ────────────────────────────────────────────────────────
ESPLORATORE_ALARM_TIME  = 4.0
ESPLORATORE_SPAWN_DELAY = 2.0

# ─── Ratto Stregone ───────────────────────────────────────────────────────────
STREGONE_CHANNEL_DELAY    = 3.0
STREGONE_CHANNEL_RANGE    = 200
STREGONE_DAMAGE_REDUCTION = 0.75
STREGONE_BREAK_RANGE      = 90

# ─── Chest tiers ──────────────────────────────────────────────────────────────
CHEST_SPECIAL_GOLD = 70
CHEST_BOSS_GOLD    = 100

# ─── Lockdown ─────────────────────────────────────────────────────────────────
C_DOOR_LOCKED = (150, 35, 35)

# ─── Upgrade shop ─────────────────────────────────────────────────────────────
UPGRADE_HP_MAX_COST         = 30
UPGRADE_HP_MAX_AMOUNT       = 20
UPGRADE_ENERGY_MAX_COST     = 30
UPGRADE_ENERGY_MAX_AMOUNT   = 15
UPGRADE_HP_REGEN_COST       = 20
UPGRADE_HP_REGEN_AMOUNT     = 0.5
UPGRADE_ENERGY_REGEN_COST   = 20
UPGRADE_ENERGY_REGEN_AMOUNT = 1.0
UPGRADE_MELEE_DMG_COST      = 40
UPGRADE_MELEE_DMG_AMOUNT    = 5
