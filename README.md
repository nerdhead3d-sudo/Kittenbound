# Kittenbound

Action-RPG roguelike 2D top-down: un mago gatto esplora un dungeon
proceduralmente generato, combatte topi e scheletri stanza per stanza, e
torna in un hub centrale per potenziarsi tra un'incursione e l'altra.

## Caratteristiche

- **Hub** con vendor (Alchimista per gli upgrade, Mago per le magie, Anziano
  per la lore) e ingresso al dungeon
- **Dungeon proceduralmente generato** a stanze collegate, con stanze speciali,
  forzieri e mappa esplorabile (TAB)
- **Combattimento**: attacco melee ad arco, schivata/roll con perfect dodge
  (bullet time + critico), skill shot con marcatura nemico + balzo artiglio
- **Nemici**: diverse varianti di topi (guardia, esploratore, lancia, stregone,
  soldato, armaturato) e scheletri, con pathfinding A*
- **Progressione**: XP, livelli, oro, loot (pozioni HP/EN, monete)
- **Recall**: torna all'hub con G e rientra nel dungeon esattamente dove eri

## Struttura del progetto

```
Kittenbound/
├── main.py              # entry point - classe Game e loop principale
├── requirements.txt
└── game/
    ├── settings.py       # costanti: finestra, tile, player, nemici, loot, ecc.
    ├── asset_manager.py  # caricamento sprite/font (con fallback proceduali)
    ├── player.py         # player: movimento, combattimento, progressione
    ├── enemy.py           # nemici (topi, scheletri) e IA
    ├── projectile.py      # proiettili (skill shot, attacchi nemici)
    ├── loot.py            # oggetti raccoglibili (monete, pozioni)
    ├── room.py            # singola stanza del dungeon
    ├── dungeon.py         # generazione e gestione del dungeon a stanze
    ├── hub.py             # area hub e NPC
    └── vendor_ui.py       # interfacce dei negozi/vendor
```

Asset grafici di riferimento in `assets/tilesets/`, documentazione di design
in `docs/`.

## Avvio

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
python main.py
```

## Comandi principali

**Hub**
- `WASD` muoviti, `E` interagisci con vendor/ingresso dungeon, `ESC` esci

**Dungeon**
- `WASD` muoviti, il personaggio guarda il cursore del mouse
- `Click sinistro` attacco melee (-8 EN)
- `SPAZIO` schivata/roll (-12 EN, perfect dodge = bullet time + critico)
- `F` skill shot (-25 EN) → seconda pressione entro 1.5s = balzo artiglio sul
  nemico marcato (65 danno garantito)
- `TAB` mappa del dungeon, `G` recall all'hub, `ESC` pausa

Guida completa ai comandi in [`docs/guida_tasti.txt`](docs/guida_tasti.txt).

## Configurazione

Tutti i parametri di bilanciamento (HP, energia, danni, costi, XP per livello,
drop di loot, ecc.) si trovano in
[`game/settings.py`](game/settings.py).
