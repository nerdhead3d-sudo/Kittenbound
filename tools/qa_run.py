"""Giro di QA automatico: gioca da solo una partita guidando il ciclo vero di Game.run() con
tasti finti, frame per frame (menu, hub, negozi, pausa, impostazioni, tutte le stanze, boss,
fine piano, morte e sacca, uscita). Non apre finestre e non suona.

Uso (dalla root del progetto, in Git Bash):
    KITTEN_SAVE_DIR=/tmp/kb_qa SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy         .venv/Scripts/python.exe tools/qa_run.py [pad|ps] [demo]

    pad   simula il controller (stile Xbox)      ps    controller PlayStation
    demo  configurazione della demo pubblicata (bioma 1, finisce con "Demo finita")

KITTEN_SAVE_DIR è obbligatorio: così il giro non tocca mai i salvataggi veri.
"""
import os, sys, traceback, collections
from pathlib import Path
if not os.environ.get("KITTEN_SAVE_DIR"):
    sys.exit("Imposta KITTEN_SAVE_DIR su una cartella di prova (i salvataggi veri non si toccano).")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pygame
import main
from game import settings as s, hub as hubmod
from game.input import InputManager

PAD = "pad" in sys.argv or "ps" in sys.argv
if "demo" in sys.argv:                 # configurazione della demo pubblicata (solo in memoria)
    s.DEV_START_BIOME = 1
if "ps" in sys.argv:
    InputManager.pad_style = property(lambda self: "ps")
log = []
seen_states = collections.Counter()


def note(msg):
    log.append(msg)
    print(msg, flush=True)


class FakeClock:
    def tick(self, fps=0):
        return 16
    def get_fps(self):
        return 60.0


def press(key):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0))


def script(g):
    p = lambda: g.player
    im = InputManager.get()

    def wait(n=1):
        for _ in range(n):
            if PAD:
                im.using_controller = True
            yield

    def key(k, after=3):
        if PAD:
            im.using_controller = True
        press(k)
        yield from wait(after)

    def expect(state, what):
        if g.state != state:
            note(f"  !! {what}: atteso {state}, stato {g.state}")
        else:
            note(f"  ok {what}")

    # ── menu ──
    yield from wait(20)
    yield from key(pygame.K_RETURN)                   # salta lo splash
    expect(s.STATE_MENU, "splash saltato")
    yield from key(pygame.K_RETURN)                   # Gioca
    yield from key(pygame.K_RETURN, 10)               # slot 1 (nuovo)
    expect(s.STATE_HUB, "partita nuova -> hub")
    p().gold = 3000

    # ── negozi ──
    for pos, name in ((hubmod.VENDOR_SPELL_POS, "Mago"), (hubmod.VENDOR_STATS_POS, "Alchimista"),
                      (hubmod.VENDOR_LORE_POS, "Anziano")):
        p().pos.update(pos[0], pos[1] + 30); p().rect.center = (pos[0], pos[1] + 30)
        yield from wait(2)
        yield from key(pygame.K_e, 20)
        expect(s.STATE_VENDOR, f"{name} aperto")
        yield from key(pygame.K_DOWN)
        yield from key(pygame.K_RETURN, 10)
        yield from key(pygame.K_RETURN, 10)
        yield from key(pygame.K_ESCAPE, 5)
        expect(s.STATE_HUB, f"{name} chiuso")
    note(f"  oro dopo i negozi: {p().gold} | magie {p().spells_owned} | upgrades {p().upgrades}")

    # ── pausa + impostazioni dall'hub ──
    yield from key(pygame.K_ESCAPE, 10)
    expect(s.STATE_INVENTORY, "pausa nell'hub")
    for _ in range(5):
        yield from key(pygame.K_DOWN, 2)
    yield from key(pygame.K_RETURN, 15)
    expect(s.STATE_SETTINGS, "impostazioni in partita")
    yield from key(pygame.K_ESCAPE, 5)
    yield from key(pygame.K_ESCAPE, 5)
    expect(s.STATE_HUB, "ritorno all'hub")

    # ── ingresso nel dungeon ──
    ex, ey = hubmod.ENTRANCE_POS
    p().pos.update(ex, ey + 20); p().rect.center = (ex, ey + 20)
    yield from wait(2)
    yield from key(pygame.K_e, 10)
    expect(s.STATE_DUNGEON_CONFIRM, "scelta del piano")
    yield from key(pygame.K_RETURN, 40)
    expect(s.STATE_PLAYING, "dentro al dungeon")

    # ── giro di tutte le stanze ──
    d = g.dungeon
    p().hp_max = p().hp = 10 ** 6
    visited = set()
    order = [d.current_pos]
    stack = [d.current_pos]
    while stack:                                       # visita in profondità della griglia
        cur = stack.pop()
        if cur in visited:
            continue
        visited.add(cur)
        order.append(cur)
        for dc, dr in ((0, -1), (0, 1), (1, 0), (-1, 0)):
            nxt = (cur[0] + dc, cur[1] + dr)
            if nxt in d.grid and nxt not in visited:
                stack.append(nxt)
    rooms_done = 0
    for target in order:
        if g.state != s.STATE_PLAYING:
            break
        d.current_pos = target
        room = d.current_room
        room.enter(p(), None)
        yield from wait(20)                            # i nemici si muovono, attaccano
        for _ in range(3):                             # graffi veri contro chi è vicino
            if room.enemies:
                e = next(iter(room.enemies))
                p().pos.update(e.pos.x - 30, e.pos.y); p().rect.center = (round(e.pos.x - 30), round(e.pos.y))
                p()._attack_buffer = 0.2
            yield from wait(12)
        for e in list(room.enemies):                   # poi si finisce in fretta
            e.hp = 1
            room.apply_single_damage(e, 9999, p())
        yield from wait(30)
        if room.has_chest and not room.chest_opened:
            cx, cy = room.pixel_w // 2, room.pixel_h // 2
            p().pos.update(cx, cy + 10); p().rect.center = (cx, cy + 10)
            yield from wait(20)
        for item in list(room.loot):                   # raccoglie quello che c'è
            p().pos.update(item.rect.centerx, item.rect.centery); p().rect.center = item.rect.center
            yield from wait(3)
        if room.merchant is not None and room.merchant.revealed:
            m = room.merchant
            p().pos.update(m.pos.x, m.pos.y + 20); p().rect.center = (round(m.pos.x), round(m.pos.y + 20))
            yield from wait(2)
            yield from key(pygame.K_e, 10)
            expect(s.STATE_MERCHANT, "mercante aperto")
            yield from key(pygame.K_RETURN, 10)
            yield from key(pygame.K_ESCAPE, 5)
        rooms_done += 1
        if target == d.current_pos and g.state == s.STATE_PLAYING:   # mappa tenuta un attimo
            yield from key(pygame.K_TAB, 2)
            yield from key(pygame.K_TAB, 2)
    note(f"  stanze girate: {rooms_done}/{len(d.grid)} | tutte liberate: {d.all_rooms_cleared} | stato {g.state}")
    yield from wait(10)
    if g.state not in (s.STATE_FLOOR_COMPLETE, s.STATE_DEMO_END):
        note(f"  !! fine piano non scattata (stato {g.state})")
    else:
        note(f"  ok fine piano: {g.state}")
    equip = dict(p().equipment)
    note(f"  equipaggiamento: {equip} | zaino {p().backpack}")

    # ── torna all'hub (ESC = senza Audacia) poi piano 2 ──
    yield from key(pygame.K_ESCAPE, 30)
    note(f"  dopo ESC a fine piano: {g.state}")
    if g.state in (s.STATE_DEMO_END, s.STATE_MENU):          # demo: dopo il boss si torna al menu
        note(f"  demo finita -> {g.state}")
        return
    ex, ey = hubmod.ENTRANCE_POS
    p().pos.update(ex, ey + 20); p().rect.center = (ex, ey + 20)
    yield from wait(2)
    yield from key(pygame.K_e, 10)
    yield from key(pygame.K_RETURN, 30)
    note(f"  piano scelto: bioma {g.biome} piano {g.floor} stato {g.state}")

    # ── morte ──
    p().gold = 123
    p().hp = 1
    p()._invincible_timer = 0
    p().nine_lives_timer = 0
    p().take_damage(50)
    yield from wait(30)
    expect(s.STATE_DEAD, "morte")
    note(f"  sacca: {g.lost_bag}")
    yield from key(pygame.K_RETURN, 30)
    note(f"  dopo Riprova: {g.state} | oro {p().gold} | equip tenuto {dict(p().equipment) == equip}")

    # ── esci dal gioco dal menu di pausa ──
    yield from key(pygame.K_ESCAPE, 10)
    yield from key(pygame.K_UP, 3)
    yield from key(pygame.K_RETURN, 3)
    note(f"  Esci dal gioco: running {g.running}")
    yield from wait(5)


def run():
    g = main.Game()
    g.clock = FakeClock()
    gen = script(g)
    flips = [0]
    orig_flip = pygame.display.flip

    def flip():
        flips[0] += 1
        seen_states[g.state] += 1
        try:
            next(gen)
        except StopIteration:
            g.running = False
        orig_flip()
    pygame.display.flip = flip
    try:
        g.run()
    except SystemExit:
        pass
    note(f"frame giocati: {flips[0]} | stati visti: {dict(seen_states)}")


try:
    run()
    print("QA FINITO SENZA CRASH")
except Exception:
    traceback.print_exc()
    print("QA: CRASH")
