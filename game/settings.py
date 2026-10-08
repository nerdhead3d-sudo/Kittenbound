# ─── Window ───────────────────────────────────────────────────────────────────
SCREEN_W = 1280
SCREEN_H = 720
FPS = 60
FULLSCREEN = True          # schermo intero all'avvio (F11 / Alt+Invio per cambiare)
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
PLAYER_HP_REGEN           = 0.25    # quasi niente: gli HP si recuperano con pozioni e forzieri

# ─── Energy costs ─────────────────────────────────────────────────────────────
PLAYER_ENERGY_MELEE_COST  = 8
PLAYER_ENERGY_DODGE_COST  = 12
PLAYER_ENERGY_SPELL_COST  = 40      # niente cooldown: il limite è l'energia

# ─── Leveling ─────────────────────────────────────────────────────────────────
XP_PER_LEVEL           = [0, 150, 400, 750, 1200, 1800, 2600, 3600]   # roguelike: curva lunga
HP_BONUS_PER_LEVEL     = 15
ENERGY_BONUS_PER_LEVEL = 10

# ─── Spell ────────────────────────────────────────────────────────────────────
SPELL_FIREBALL_SPEED  = 380
SPELL_FIREBALL_RADIUS = 8
SPELL_SHOT_SPEED      = 480
SPELL_SHOT_DAMAGE     = 15
SPELL_MARK_DURATION   = 1.5
SPELL_CLAW_DAMAGE     = 65
SPELL_SHOT_COOLDOWN   = 0.0     # nessun cooldown: la spell costa tanta energia

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

# ─── Audio ────────────────────────────────────────────────────────────────────
SFX_VOLUME      = 0.7     # volume generale degli effetti (0-1)
SFX_CHANNELS    = 24      # suoni contemporanei
SFX_MIN_GAP_MS  = 45      # lo stesso effetto non riparte prima di questo intervallo

# ─── Animazioni nemici ────────────────────────────────────────────────────────
ENEMY_HITBOX_SIZE      = 36     # hitbox fissa, indipendente dalla dimensione dello sprite
ENEMY_ATTACK_STRIKE    = 3      # frame del colpo nella strip d'attacco (prima: caricamento)
ENEMY_ATTACK_RECOVER   = 0.20   # s di animazione dopo il colpo (accompagnamento + ritorno)

# ─── Dodge roll ───────────────────────────────────────────────────────────────
PLAYER_DODGE_SPEED    = 300
PLAYER_DODGE_DURATION = 0.20
PLAYER_DODGE_PERFECT  = 0.09
PLAYER_DODGE_COOLDOWN = 0.65
PLAYER_DODGE_JUMP     = 24      # altezza (px) del salto visivo durante la schivata
PLAYER_ATTACK_BUFFER  = 0.25    # attacco premuto in schivata: parte appena atterri
PLAYER_LAND_TIME      = 0.12    # schiacciamento all'atterraggio

# ─── Parata dei proiettili (Shift / tasto destro / R1-RB) ─────────────────────
PARRY_WINDOW       = 0.22    # secondi in cui i proiettili vengono respinti
PARRY_COOLDOWN     = 0.65
PARRY_ENERGY       = 10
PARRY_REFUND       = 8       # energia restituita per ogni proiettile parato
PARRY_RADIUS       = 58      # distanza a cui un proiettile viene intercettato
PARRY_DMG_MULT     = 2.0     # il proiettile respinto fa il doppio del danno
PARRY_SPEED_MULT   = 1.35
PARRY_PERFECT      = 0.09    # primi istanti della parata: parata perfetta
PARRY_COUNTER_MULT = 2.5     # contrattacco automatico (x danno melee) dopo una parata perfetta
PARRY_PERFECT_PROJ = 3.0     # proiettile respinto con parata perfetta: danno x3
PARRY_KNIFE_MULT   = (0.6, 1.0)   # coltelli del boss respinti (normale, perfetta): sono 5, già tanti
PERFECT_FLASH_TIME = 0.12    # lampo a schermo della schivata perfetta

# ─── Enemy ────────────────────────────────────────────────────────────────────
ENEMY_CHASE_RANGE      = 320
ENEMY_AGGRO_RANGE      = 430     # ti vedono (linea libera) entro questa distanza → ti inseguono per sempre
ENEMY_ALERT_RANGE      = 280     # chi prende aggro avvisa i compagni entro questo raggio
ENEMY_ATTACK_RANGE     = 60
ENEMY_ATTACK_COOLDOWN  = 1.2
ENEMY_WINDUP_TIME      = 0.30
ENEMY_PROJECTILE_SPEED = 260
ENEMY_PROJECTILE_RANGE = 400

# ─── Loot ─────────────────────────────────────────────────────────────────────
COIN_VALUE          = 1
POTION_HP_VALUE     = 30
POTION_ENERGY_VALUE = 25
LOOT_RADIUS         = 10

# ─── Pozioni di vita (inventario, tasto Q) ────────────────────────────────────
POTION_START     = 3       # pozioni all'inizio della partita
POTION_MAX       = 5       # capienza della borsa
POTION_HEAL      = 40
POTION_COST      = 30      # prezzo fisso dall'Alchimista
POTION_COOLDOWN  = 0.6

# ─── Pallini rossi (drop dei nemici: cura piccola) ────────────────────────────
ORB_HEAL         = 3
ORB_DROP_CHANCE  = 0.65    # probabilità che un nemico ne lasci
ORB_DROP_MAX     = 2       # da 1 a ORB_DROP_MAX pallini
ORB_MAGNET_RANGE = 95      # entro questa distanza volano verso il gatto
ORB_MAGNET_SPEED = 380
GOLD_DROP_MIN       = 1
GOLD_DROP_MAX       = 3
POTION_HP_CHANCE    = 0.0     # le pozioni di vita non si trovano: si comprano
POTION_EN_CHANCE    = 0.07
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
LIGHT_RADIUS    = 250               # alone di luce attorno al gatto
DARKNESS_ALPHA  = 215               # buio lontano dalle luci (0 = niente buio, 255 = nero)
TORCH_LIGHT_RADIUS = 170            # luce delle torce a muro
PLAYER_GLOW     = 38                # luce calda in più vicino al gatto (0 = spenta)

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
BOSS_DAMAGE_MELEE       = 26
BOSS_DAMAGE_CHARGE      = 50      # se la carica ti prende fa malissimo
BOSS_SPEED_PATROL       = 135
BOSS_CHARGE_SPEED       = 780
BOSS_CHARGE_RANGE       = 430     # carica da questa distanza in giù
BOSS_WINDUP_TIME        = 0.50    # finestra per reagire alla carica
BOSS_WINDUP_RAGE_TIME   = 0.32
BOSS_STUN_DURATION      = 1.1     # finestra per colpirlo: breve
BOSS_STUN_RAGE_DURATION = 0.7
BOSS_CHARGE_CD          = 2.2     # dopo lo stordimento
BOSS_CHARGE_RAGE_CD     = 1.4

# Coltelli a distanza (se resti lontano): stessa animazione della raffica ravvicinata
BOSS_SHOT_MIN_DIST      = 190
BOSS_SHOT_WINDUP        = 0.50
BOSS_SHOT_RAGE_WINDUP   = 0.38
BOSS_SHOT_COOLDOWN      = 1.0
BOSS_SHOT_RAGE_COOLDOWN = 0.65
BOSS_SHOT_SPEED         = 600
BOSS_SHOT_DAMAGE        = 18
BOSS_SHOT_COUNT         = 3       # ventaglio
BOSS_SHOT_RAGE_COUNT    = 5       # in furia: ventaglio più largo
BOSS_SHOT_SPREAD        = 13      # gradi tra un proiettile e l'altro

# Pioggia di massi: il boss pesta il terreno, i massi cadono dove c'è la loro ombra
BOSS_SLAM_TIME          = 0.55    # pestone prima della pioggia
BOSS_ROCK_COOLDOWN      = 7.5
BOSS_ROCK_RAGE_COOLDOWN = 4.5
BOSS_ROCK_COUNT         = 11      # piovono su tutta la stanza
BOSS_ROCK_RAGE_COUNT    = 15
BOSS_ROCK_WARN          = 1.6     # secondi di ombra prima dell'impatto (tempo per spostarsi)
BOSS_ROCK_RAGE_WARN     = 1.3
BOSS_ROCK_DAMAGE        = 42
BOSS_ROCK_RADIUS        = 36
BOSS_ROCK_MIN_GAP       = 95      # distanza minima tra due massi: resta sempre un varco
BOSS_ROCK_STAGGER       = 0.07    # i massi cadono uno dopo l'altro
BOSS_RAGE_THRESHOLD     = 0.30
# Raffica di coltelli: quando ti avvicini carica 5 coltelli che gli fluttuano attorno, poi partono
BOSS_KNIFE_RANGE         = 200     # distanza a cui la usa
BOSS_KNIFE_WINDUP        = 0.65
BOSS_KNIFE_RAGE_WINDUP   = 0.45
BOSS_KNIFE_COUNT         = 5
BOSS_KNIFE_SPREAD        = 11      # gradi tra un coltello e l'altro
BOSS_KNIFE_SPEED         = 650
BOSS_KNIFE_DAMAGE        = 20
BOSS_KNIFE_COOLDOWN      = 5.0
BOSS_KNIFE_RAGE_COOLDOWN = 3.2
BOSS_FEINT_CHANCE       = 0.45

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
STREGONE_CHANNEL_RANGE    = 220     # protegge i ratti entro questo raggio finché è vivo
STREGONE_DAMAGE_REDUCTION = 0.70
STREGONE_BREAK_RANGE      = 90      # se gli stai addosso la protezione cade
STREGONE_INTERRUPT        = 3.0     # secondi senza protezione dopo che lo colpisci
STREGONE_KEEP_DIST        = (140, 240)   # resta dietro ai compagni

# ─── Chest tiers ──────────────────────────────────────────────────────────────
CHEST_SPECIAL_GOLD = 12
CHEST_BOSS_GOLD    = 30

# ─── Scaling per piano (piano 1 = base) ───────────────────────────────────────
FLOOR_HP_SCALE     = 0.35    # +35% HP nemici per ogni piano
FLOOR_DMG_SCALE    = 0.25    # +25% danni nemici per piano
FLOOR_REWARD_SCALE = 0.30    # +30% oro e XP per piano

# ─── Ratto Fromboliere (nemico a distanza) ────────────────────────────────────
SLINGER_WINDUP     = 0.30    # breve caricamento del lancio (nessuna linea di mira)
SLINGER_PROJ_SPEED = 340
SLINGER_PROJ_RANGE = 560
SLINGER_MIN_DIST   = 160     # sotto questa distanza indietreggia
SLINGER_MAX_DIST   = 300     # sopra questa distanza si avvicina

# ─── Lockdown ─────────────────────────────────────────────────────────────────
C_DOOR_LOCKED = (150, 35, 35)

# ─── Upgrade shop ─────────────────────────────────────────────────────────────
UPGRADE_COST_GROWTH         = 1.7     # ogni acquisto dello stesso potenziamento costa x1.7
UPGRADE_HP_MAX_COST         = 30
UPGRADE_HP_MAX_AMOUNT       = 20
UPGRADE_ENERGY_MAX_COST     = 30
UPGRADE_ENERGY_MAX_AMOUNT   = 15
UPGRADE_HP_REGEN_COST       = 35
UPGRADE_HP_REGEN_AMOUNT     = 0.25
UPGRADE_ENERGY_REGEN_COST   = 25
UPGRADE_ENERGY_REGEN_AMOUNT = 1.0
UPGRADE_MELEE_DMG_COST      = 45
UPGRADE_MELEE_DMG_AMOUNT    = 5

# NPC dell'hub: si girano verso il gatto quando è vicino
NPC_LOOK_RANGE = 260       # px
NPC_TURN_SPEED = 200       # gradi al secondo

# ─── Magie (game/spells.py): 2 equipaggiate alla volta, nessun cooldown ───────
SPELL_BLADE_COST    = 30       # Graffio Spettrale: 3 lame che trapassano i nemici
SPELL_BLADE_PRICE   = 60
SPELL_BLADE_DAMAGE  = 20
SPELL_BLADE_SPEED   = 560
SPELL_BLADE_RANGE   = 300
SPELL_BLADE_SPREAD  = 16       # gradi tra le lame
SPELL_HISS_COST     = 30       # Soffio: cono che respinge nemici e proiettili
SPELL_HISS_PRICE    = 70
SPELL_HISS_RANGE    = 150
SPELL_HISS_ARC      = 140      # gradi
SPELL_HISS_PUSH     = 120      # px di spinta
SPELL_HISS_DAMAGE   = 8
SPELL_SIGHT_COST    = 25       # Occhi nel Buio: niente buio e nemici in vista
SPELL_SIGHT_PRICE   = 50
SPELL_SIGHT_TIME    = 8.0
SPELL_SHADOW_COST   = 40       # Ombra Felina: un'ombra attira i nemici
SPELL_SHADOW_PRICE  = 90
SPELL_SHADOW_TIME   = 4.0
SPELL_SHADOW_HITS   = 3
SPELL_SHADOW_SPEED  = 115      # l'ombra gira per la stanza (lenta: i nemici le stanno dietro)
SPELL_LIVES_COST    = 45       # Nove Vite: il colpo mortale lascia a 1 HP
SPELL_LIVES_PRICE   = 120
SPELL_LIVES_TIME    = 8.0

# ─── TEST ─────────────────────────────────────────────────────────────────────
# !!! DA RIMETTERE A 0 PRIMA DI FARE IL FILE INSTALLABILE !!!
# Oro iniziale alto solo per provare tutte le magie e i potenziamenti.
START_GOLD = 9999
