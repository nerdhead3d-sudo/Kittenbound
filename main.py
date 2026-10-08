import math
import random
import sys
import pygame
from game import settings as s
from game.asset_manager import AssetManager
from game.player import Player
from game.dungeon import Dungeon
from game.room import TILE_FLOOR
from game.hub import Hub
from game.vendor_ui import VendorUI
from game.projectile import Projectile
from game.loot import Loot
from game.merchant import MerchantUI
from game.sound import SoundManager, play
from game.input import InputManager
from game import gfx
from game import spells
from game import controls_panel
from game import save
from game import user_settings as us
from game.menu import MainMenu
from game.inventory_ui import InventoryUI
from game import equipment
from game import hud
from game.enemy import TopoArmaturato
import time


class Game:
    """Nucleo del gioco: loop principale e gestione stati."""

    def __init__(self):
        pygame.mixer.pre_init(44100, -16, 2, 512)   # buffer piccolo: suoni senza ritardo
        pygame.init()
        pygame.display.set_caption(s.TITLE)

        us.load()
        us.apply_quality_env()                      # qualità grafica scelta nel menu
        self.fullscreen = us.get("fullscreen")
        self.slot       = None                      # slot di salvataggio in uso (None = nel menu)
        self.kept_gear  = None                      # equipaggiamento che sopravvive alla morte
        self.progress   = self._new_progress()       # piani raggiunti, mercanti trovati, boss battuti
        self._floor_sel = (1, 1)                    # scelta all'ingresso del dungeon
        self.inventory_ui = None
        self._inv_return  = None                    # stato a cui torna il menu equipaggiamento
        self._fade      = 0.0                       # dissolvenza dal nero entrando in partita
        self._banner    = None                      # [titolo, sottotitolo, tempo rimasto, durata]
        self.lost_bag   = None      # {"floor", "room", "pos", "gold"}: lasciata morendo (l'Audacia invece è persa)
        self.run_seed   = random.randrange(1 << 30)   # seme dei piani: ogni piano si genera una volta sola
        gfx.setup((s.SCREEN_W, s.SCREEN_H))          # HD: K = 2 su schermi 2560x1440
        self._set_display()
        self.clock   = pygame.time.Clock()
        self.running = True

        assets = AssetManager.get()
        self.font_large = assets.font(48, bold=True)
        self.font_small = assets.font(22)
        self.font_tiny  = assets.font(16)

        self._init_session()
        SoundManager.get().master = us.get("volume") / 10
        self.menu      = MainMenu()
        self.state     = s.STATE_MENU
        self._save_sig = self._autosave_signature()
        self._bt_vignette = self._make_bt_vignette()

    def _set_display(self):
        """SCALED: il gioco disegna sempre a 1280x720 e pygame lo scala alla finestra o
        allo schermo intero mantenendo le proporzioni (e converte le coordinate del mouse)."""
        logical = (s.SCREEN_W, s.SCREEN_H)
        size    = (s.SCREEN_W * gfx.K, s.SCREEN_H * gfx.K)   # risoluzione reale di disegno
        flags   = pygame.SCALED | (pygame.FULLSCREEN if self.fullscreen else 0)
        try:
            display = pygame.display.set_mode(size, flags)
        except pygame.error:              # nessun renderer (es. driver video minimale)
            display = pygame.display.set_mode(size)
        self.screen = gfx.wrap_display(display, logical)

    def _init_session(self):
        """Reset completo: hub, player, nessun dungeon attivo."""
        self.hub       = Hub()
        self.dungeon   = None
        self.vendor_ui = VendorUI()
        self.merchant_ui = MerchantUI()
        self.player_projectiles = pygame.sprite.Group()

        self.player = Player(float(s.SCREEN_W // 2), float(s.SCREEN_H // 2))
        equipment.restore(self.player, getattr(self, "kept_gear", None))
        self.hub.enter(self.player)

        self.recall_room_pos   = None   # (col,row) salvata al G recall
        self.recall_player_pos = None   # (x,y) world salvata al G recall

        self.biome               = s.DEV_START_BIOME   # 1 = Bosco, 2 = Fogne (vedi s.BIOMES)
        self.floor               = 1     # piano corrente del bioma (1-BOSCO_FLOORS)
        self._floor_complete     = False  # True dopo che all_rooms_cleared scatta
        self._pending_floor      = None  # piano da caricare al prossimo ingresso dall'hub

        self.state    = s.STATE_HUB
        self.show_map = False

    # ── Loop ──────────────────────────────────────────────────────────────────

    def _make_bt_vignette(self) -> pygame.Surface:
        vign = gfx.Surface((s.SCREEN_W, s.SCREEN_H), pygame.SRCALPHA)
        for i in range(22):
            alpha = int(80 * (1 - i / 22))
            pygame.draw.rect(vign, (80, 240, 200, alpha),
                             (i, i, s.SCREEN_W - i * 2, s.SCREEN_H - i * 2), 1)
        return vign

    def run(self):
        while self.running:
            dt = min(self.clock.tick(s.FPS) / 1000.0, 0.05)
            self._autosave()

            self._handle_events()

            if self.state == s.STATE_MENU:
                self.menu.update(dt)
                self.menu.draw(self.screen, dt)
            elif self.state == s.STATE_HUB:
                self._update_hub(dt)
                self._draw_hub()
            elif self.state == s.STATE_VENDOR:
                self.vendor_ui.update(dt)
                self._draw_hub()
                self.vendor_ui.draw(self.screen, self.player)
            elif self.state == s.STATE_DUNGEON_CONFIRM:
                self._draw_hub()
                self._draw_dungeon_confirm()
            elif self.state == s.STATE_PLAYING:
                self._update(dt)
                self._draw()
            elif self.state == s.STATE_FLOOR_COMPLETE:
                self._draw()
                self._draw_floor_complete_overlay()
            elif self.state == s.STATE_INVENTORY:
                self.inventory_ui.update(dt)
                if self._inv_return == s.STATE_HUB:
                    self._draw_hub()
                else:
                    self._draw()
                self.inventory_ui.draw(self.screen, self.player)
            elif self.state == s.STATE_MERCHANT:
                self.merchant_ui.update(dt)
                self._draw()
                self.merchant_ui.draw(self.screen, self.player)
            elif self.state == s.STATE_DEMO_END:
                self._draw()
                hud.modal(self.screen, "Demo finita", "Grazie per aver giocato!",
                          [("confirm", "Menu principale")])
            elif self.state == s.STATE_DEAD:
                self._draw()
                bag = self.lost_bag
                hud.modal(self.screen, "Sei morto", "",
                          [("confirm", "Riprova"), ("back", "Menu")], accent=(220, 80, 80),
                          extra=f"Sacca con {bag['gold']} oro al piano {bag['floor']}" if bag else "")
            elif self.state == s.STATE_PAUSE:
                self._draw()
                hud.modal(self.screen, "Pausa", "", [("confirm", "Continua"), ("back", "Menu principale")])

            if (self.show_map or InputManager.get().map_held()) and self.state == s.STATE_PLAYING:
                self._draw_map_overlay()

            if self._fade > 0:                                 # dissolvenza entrando in partita
                veil = gfx.Surface((s.SCREEN_W, s.SCREEN_H))
                veil.fill((0, 0, 0))
                veil.set_alpha(round(255 * min(1.0, self._fade / 0.6)))
                self.screen.blit(veil, (0, 0))
                self._fade = max(0.0, self._fade - dt)

            pygame.display.flip()

        self._save()                                # chiudendo si salva sempre
        pygame.quit()
        sys.exit()

    # ── Events ────────────────────────────────────────────────────────────────

    def _handle_events(self):
        pad = InputManager.get()
        for event in pad.events():
            action = pad.handle_event(event)
            if action:
                key = self._pad_key(action)
                if key is not None:
                    self._on_key(key)
                continue
            if event.type == pygame.QUIT:
                self.running = False

            elif event.type == pygame.KEYDOWN:
                self._on_key(event.key, getattr(event, "mod", 0))

            elif (event.type == pygame.MOUSEBUTTONDOWN and event.button == 3
                  and self.state == s.STATE_PLAYING):
                self.player.try_parry()                 # tasto destro: parata

    _NAV = {"nav_up": pygame.K_UP, "nav_down": pygame.K_DOWN,
            "nav_left": pygame.K_LEFT, "nav_right": pygame.K_RIGHT}

    def _pad_key(self, action: str) -> "int | None":
        """Traduce un pulsante del controller nel tasto equivalente per lo stato attuale."""
        st = self.state
        if action in self._NAV:                    # levetta: solo nei menu
            menus = (s.STATE_MENU, s.STATE_INVENTORY, s.STATE_VENDOR, s.STATE_MERCHANT,
                     s.STATE_DUNGEON_CONFIRM)
            return self._NAV[action] if st in menus else None
        if st == s.STATE_PLAYING:
            # □ attacco (tenuto), ✕ schivata, △ / ○ magie, R1 parata, L2 pozione, L1 mappa (tenuto)
            return {"confirm": pygame.K_SPACE, "dodge": pygame.K_q,
                    "spell": pygame.K_f, "back": pygame.K_r, "down": pygame.K_g, "map": pygame.K_i,
                    "parry": pygame.K_LSHIFT,
                    "pause": pygame.K_ESCAPE}.get(action)
        if st == s.STATE_MENU:
            return {"confirm": pygame.K_RETURN, "back": pygame.K_ESCAPE, "spell": pygame.K_DELETE,
                    "up": pygame.K_UP, "down": pygame.K_DOWN,
                    "left": pygame.K_LEFT, "right": pygame.K_RIGHT}.get(action)
        if st == s.STATE_PAUSE:
            return {"pause": pygame.K_p, "confirm": pygame.K_p, "back": pygame.K_ESCAPE}.get(action)
        if st == s.STATE_DEAD:
            return {"confirm": pygame.K_r, "back": pygame.K_ESCAPE}.get(action)
        if st == s.STATE_HUB:
            return {"confirm": pygame.K_e, "map": pygame.K_i,
                    "pause": pygame.K_ESCAPE}.get(action)   # B nell'hub non chiude il gioco
        if st == s.STATE_INVENTORY:
            return {"confirm": pygame.K_RETURN, "back": pygame.K_ESCAPE, "map": pygame.K_i, "pause": pygame.K_ESCAPE,
                    "up": pygame.K_UP, "down": pygame.K_DOWN,
                    "left": pygame.K_LEFT, "right": pygame.K_RIGHT}.get(action)
        if st == s.STATE_MERCHANT:
            return {"confirm": pygame.K_RETURN, "back": pygame.K_ESCAPE,
                    "up": pygame.K_UP, "down": pygame.K_DOWN}.get(action)
        if st == s.STATE_VENDOR:
            return {"confirm": pygame.K_RETURN, "back": pygame.K_ESCAPE, "spell": pygame.K_RETURN,
                    "attack": pygame.K_r, "up": pygame.K_UP, "down": pygame.K_DOWN}.get(action)
        if st == s.STATE_DEMO_END:
            return pygame.K_RETURN if action in ("confirm", "back", "pause") else None
        if st == s.STATE_DUNGEON_CONFIRM:
            return {"confirm": pygame.K_RETURN, "back": pygame.K_ESCAPE, "up": pygame.K_UP,
                    "down": pygame.K_DOWN, "left": pygame.K_LEFT, "right": pygame.K_RIGHT}.get(action)
        if st == s.STATE_FLOOR_COMPLETE:
            return {"confirm": pygame.K_RETURN, "back": pygame.K_ESCAPE}.get(action)
        return None

    def _on_key(self, key: int, mod: int = 0):
        """Azione di un tasto (o di un pulsante del controller già tradotto)."""
        alt_enter = key == pygame.K_RETURN and mod & pygame.KMOD_ALT
        if key == pygame.K_F11 or alt_enter:
            self.fullscreen = not self.fullscreen
            us.set("fullscreen", self.fullscreen)
            self._set_display()
            return
        if self.state == s.STATE_MENU:
            action = self.menu.handle_key(key)
            if isinstance(action, tuple) and action[0] == "play":
                self._start_slot(action[1])
            elif action == "quit":
                self.running = False
            elif action == "display":
                self.fullscreen = us.get("fullscreen")
                self._set_display()
            elif action == "audio":
                SoundManager.get().master = us.get("volume") / 10
            return
        if key == pygame.K_m:
            SoundManager.get().toggle_mute()
            return
        if key in (pygame.K_RETURN, pygame.K_SPACE) and self.state == s.STATE_DEAD:
            self._restart()
            return
        if key in (pygame.K_RETURN, pygame.K_SPACE) and self.state == s.STATE_PAUSE:
            self.state = s.STATE_PLAYING
            return
        if self.state == s.STATE_INVENTORY:               # equipaggiamento = pausa
            action = self.inventory_ui.handle_key(key, self.player)
            if action:
                self.state = self._inv_return
            if action == "menu":
                self._to_menu()
            elif action == "quit":
                self.running = False                       # si salva all'uscita dal ciclo
            return
        if key in (pygame.K_i, pygame.K_ESCAPE) and self.state in (s.STATE_PLAYING, s.STATE_HUB):
            if self.inventory_ui is None:
                self.inventory_ui = InventoryUI()
            self._inv_return = self.state
            self.inventory_ui.open()
            self.state = s.STATE_INVENTORY
            return
        if self.state == s.STATE_MERCHANT:                # negozio del mercante nascosto
            if self.merchant_ui.handle_key(key, self.player, self.dungeon):
                play("ui_open", 0.6)
                self.state = s.STATE_PLAYING
            return
        # parlare col mercante: E, oppure ✕ (che altrimenti è la schivata) quando gli sei vicino
        if (self.state == s.STATE_PLAYING and key in (pygame.K_e, pygame.K_SPACE) and self.dungeon
                and (m := self.dungeon.current_room.merchant) is not None and m.near(self.player)):
            play("ui_open", 0.6)
            self.merchant_ui.open(m)
            self.state = s.STATE_MERCHANT
            return
        # Il vendor intercetta tutti i tasti
        if self.state == s.STATE_VENDOR:
            if self.vendor_ui.handle_key(key, self.player):
                play("ui_open", 0.6)
                self.state = s.STATE_HUB

        elif self.state == s.STATE_DEMO_END:
            if key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                self._to_menu()                            # fine della demo: si torna al menu

        elif self.state == s.STATE_FLOOR_COMPLETE:
            if key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.floor < s.BOSCO_FLOORS:
                    self.player.add_audacia(s.AUDACIA_PER_FLOOR)     # avanti senza tornare: audace
                    self._advance_floor()
                else:
                    self._complete_biome()
            elif key in (pygame.K_ESCAPE, pygame.K_g):
                self.player.lose_audacia()
                if self.floor < s.BOSCO_FLOORS:
                    self._pending_floor = self.floor + 1
                    self._mark_reached(self.biome, self.floor + 1)
                self._floor_complete   = False
                self.recall_room_pos   = None
                self.recall_player_pos = None
                self.hub.gate_active   = False
                self.player_projectiles.empty()
                self.hub.enter_from_dungeon(self.player)
                self.state = s.STATE_HUB

        elif self.state == s.STATE_DUNGEON_CONFIRM:
            if key in (pygame.K_RETURN, pygame.K_SPACE):
                self._enter_floor(*self._floor_sel)
            elif key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                self.state = s.STATE_HUB
            elif key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d):
                self._move_floor_sel(-1 if key in (pygame.K_LEFT, pygame.K_a) else 1, 0)
            elif key in (pygame.K_UP, pygame.K_w, pygame.K_DOWN, pygame.K_s):
                self._move_floor_sel(0, -1 if key in (pygame.K_UP, pygame.K_w) else 1)

        elif key == pygame.K_ESCAPE:
            if self.state == s.STATE_PLAYING:
                self.state    = s.STATE_PAUSE
                self.show_map = False
            else:                                          # pausa, hub, morte: menu principale
                self._to_menu()

        elif key == pygame.K_TAB:
            if self.state == s.STATE_PLAYING:
                self.show_map = not self.show_map

        elif key == pygame.K_p:
            if self.state == s.STATE_PAUSE:
                self.state = s.STATE_PLAYING

        elif key == pygame.K_r:
            if self.state == s.STATE_DEAD:
                self._restart()
            elif self.state == s.STATE_PLAYING:
                self._cast_slot(1)

        elif key == pygame.K_e:
            if self.state == s.STATE_HUB:
                interaction = self.hub.get_interaction(self.player.pos)
                if interaction:
                    play("ui_open", 0.6)
                if interaction == 'vendor_spell':
                    self.vendor_ui.open('spell')
                    self.state = s.STATE_VENDOR
                elif interaction == 'vendor_stats':
                    self.vendor_ui.open('stats')
                    self.state = s.STATE_VENDOR
                elif interaction == 'vendor_lore':
                    self.vendor_ui.open('lore')
                    self.state = s.STATE_VENDOR
                elif interaction == 'entrance':
                    self._floor_sel = self._default_floor_sel()
                    self.state = s.STATE_DUNGEON_CONFIRM
                elif interaction == 'gate':
                    self._enter_dungeon_via_gate()

        elif key == pygame.K_SPACE:
            if self.state == s.STATE_PLAYING:
                self.player.try_dodge(InputManager.get().move_vector())

        elif key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
            if self.state == s.STATE_PLAYING:
                self.player.try_parry()

        elif key == pygame.K_q:
            if self.state == s.STATE_PLAYING and not self.player.drink_potion():
                if self.player.potions <= 0:
                    play("error", 0.5)

        elif key == pygame.K_f:
            if self.state == s.STATE_PLAYING:
                self._cast_slot(0)

        elif key == pygame.K_g:
            if self.state == s.STATE_PLAYING and self.dungeon:
                self.recall_room_pos   = self.dungeon.current_pos
                self.recall_player_pos = (self.player.pos.x, self.player.pos.y)
                self.hub.activate_gate()
                self.player.cancel_spell()
                self.player.lose_audacia()
                play("recall", 0.8)
                self.player_projectiles.empty()
                self.hub.enter_from_dungeon(self.player)
                self.state = s.STATE_HUB

    # ── Hub ───────────────────────────────────────────────────────────────────

    def _update_hub(self, dt: float):
        self.player.update(dt, wall_rects=self.hub.obstacles)
        margin = float(s.PLAYER_RADIUS + 20)
        self.player.pos.x = max(margin, min(float(s.SCREEN_W) - margin, self.player.pos.x))
        self.player.pos.y = max(margin, min(float(s.SCREEN_H) - margin, self.player.pos.y))
        self.player.rect.center = (round(self.player.pos.x), round(self.player.pos.y))

    def _draw_hub(self):
        self.hub.draw(self.screen, self.player)     # disegna anche il gatto, ordinato per Y
        self._draw_hub_hud()

    def _draw_hub_hud(self):
        hud.draw_status(self.screen, self.player, spells_too=False)
        hud.draw_notice(self.screen, self.player.notice)
        self._draw_fps()

    def _draw_fps(self):
        if us.get("show_fps"):
            img = AssetManager.get().font(14).render(f"{self.clock.get_fps():.0f} FPS", True, (150, 146, 160))
            self.screen.blit(img, img.get_rect(right=s.SCREEN_W - 12, top=8))


    def _spell_direction(self) -> pygame.math.Vector2:
        """Dove lanciare: col controller lo stick destro, poi il sinistro, poi il muso;
        con mouse e tastiera verso il cursore."""
        pad = InputManager.get()
        if pad.using_controller:
            direction = pad.aim_vector()
            if direction is None:
                move = pad.move_vector()
                direction = move if move.length() > 0.3 else pygame.math.Vector2(self.player.facing)
            return direction
        cam = self.dungeon.current_room.get_camera_offset(self.player.pos)
        mx, my = pygame.mouse.get_pos()
        return pygame.math.Vector2(mx + cam[0] - self.player.pos.x, my + cam[1] - self.player.pos.y)

    def _cast_slot(self, slot: int):
        """Magia equipaggiata nello slot (0 = F / Y, 1 = R / LB)."""
        spell_id = self.player.spell_slots[slot]
        if spell_id is None:
            play("error", 0.4)
            return
        if spell_id != "claw_leap":
            spells.cast(self, spell_id, self._spell_direction())
            return
        if self.player._spell_phase == "ready":                 # Balzo Artigliato: colpo, poi balzo
            if self.player.try_cast_spell():
                direction = self._spell_direction()
                if direction.length_squared() > 0:
                    self.player.facing = direction.normalize()
                    self.player_projectiles.add(Projectile(
                        self.player.pos.x, self.player.pos.y, direction,
                        damage=s.SPELL_SHOT_DAMAGE, owner="player",
                        speed=s.SPELL_SHOT_SPEED, max_range=500.0, is_spell=True))
                    play("spell_cast", 0.8)
        elif self.player._spell_phase == "marked_ready":
            self.player.try_leap()

    def _aim_assist(self, room):
        """Controller senza stick destro: l'attacco si gira verso il nemico più vicino
        entro un cono davanti al gatto (aiuto alla mira, non automatico al 100%)."""
        best, best_d = None, 170.0
        for e in room.enemies:
            to_e = e.pos - self.player.pos
            d = to_e.length()
            if 0 < d < best_d and to_e.normalize().dot(self.player.facing) > 0.3:
                best, best_d = to_e.normalize(), d
        if best is not None:
            self.player.facing = best

    def _enter_dungeon_via_entrance(self):
        """Entrata senza scegliere: il piano proposto (in corso, quello sbloccato o l'ultimo)."""
        self._enter_floor(*self._default_floor_sel())

    def _new_dungeon(self) -> Dungeon:
        """Ogni piano si genera una volta sola: anche morendo ritrovi lo stesso dungeon.
        Il seme cambia solo quando finisci il bioma."""
        AssetManager.set_tileset(self.biome_info["tileset"])      # muri e pavimento del bioma
        self._banner = [self.biome_info["name"], f"Piano {self.floor}", 3.0, 3.0]
        d = Dungeon(floor=self.floor, seed=self.run_seed * 101 + self.biome * 13 + self.floor,
                    water=self.biome_info.get("water", False))
        self._mark_reached(self.biome, self.floor)
        key = self._floor_key()
        if key in self.progress["merchants"] and d.merchant_pos is not None:     # ricorda la merce venduta
            d.grid[d.merchant_pos].merchant.sold = set(self.progress["merchants"][key])
            d.merchant_known = True
        for pos, r in d.grid.items():                                         # forzieri già aperti: vuoti
            if f"{key}:{pos[0]},{pos[1]}" in self.progress["chests"]:
                r.chest_opened = True
        if key in self.progress["bosses"]:                                    # il boss resta battuto
            boss = d.grid[d.end_pos]
            boss.enemies.empty()
            boss.cleared      = True
            boss.chest_opened = boss.chest_opened or bool(self.progress["bosses"][key])
        return d

    # ── Piani già raggiunti ───────────────────────────────────────────────────

    @staticmethod
    def _new_progress() -> dict:
        return {"reached": {str(s.DEV_START_BIOME): 1}, "merchants": {}, "bosses": {}, "chests": []}

    def _floor_key(self, biome=None, floor=None) -> str:
        return f"{biome or self.biome}-{floor or self.floor}"

    def _mark_reached(self, biome: int, floor: int):
        r = self.progress["reached"]
        r[str(biome)] = max(r.get(str(biome), 0), min(floor, s.BOSCO_FLOORS))

    def _track_progress(self, room):
        """Ogni frame: mercante trovato (e cosa gli hai comprato), boss battuto."""
        key = self._floor_key()
        m = room.merchant
        if m is not None and m.revealed:
            self.progress["merchants"][key] = sorted(m.sold)
        if room.room_type == s.ROOM_TYPE_BOSS and room.cleared:
            self.progress["bosses"][key] = bool(room.chest_opened)
        if room.has_chest and room.chest_opened:                     # ogni forziere si apre una volta sola
            ck = f"{key}:{self.dungeon.current_pos[0]},{self.dungeon.current_pos[1]}"
            if ck not in self.progress["chests"]:
                self.progress["chests"].append(ck)

    def _default_floor_sel(self) -> tuple:
        if self.dungeon is not None and not self.dungeon.all_rooms_cleared and self._pending_floor is None:
            return (self.biome, self.floor)                     # partita in corso
        if self._pending_floor is not None:
            return (self.biome, self._pending_floor)
        return (self.biome, self.progress["reached"].get(str(self.biome), 1))

    def _move_floor_sel(self, dx: int, dy: int):
        """Su e giù (anche sinistra/destra) nella lista dei piani raggiunti."""
        entries = hud.floor_entries(self.progress["reached"])
        if not entries:
            return
        cur = tuple(self._floor_sel)
        i = entries.index(cur) if cur in entries else 0
        i = max(0, min(len(entries) - 1, i + (dy or dx)))
        if entries[i] != cur:
            play("ui_open", 0.25)
        self._floor_sel = entries[i]

    def _enter_floor(self, biome: int, floor: int):
        """Entra nel piano scelto: se è quello in corso si riprende, altrimenti si rigenera
        dal seme (stesso piano di sempre, nemici di nuovo al loro posto, boss no)."""
        resume = (self.dungeon is not None and (biome, floor) == (self.biome, self.floor)
                  and not self.dungeon.all_rooms_cleared)
        if resume:
            self.dungeon.current_pos = self.dungeon.start_pos
            self.dungeon.current_room.visited = True
        else:
            self.biome, self.floor = biome, floor
            self._pending_floor    = None
            self._floor_complete   = False
            self.dungeon           = self._new_dungeon()
            self._place_lost_bag()
            self.recall_room_pos   = None
            self.recall_player_pos = None
            self.hub.gate_active   = False
        room = self.dungeon.current_room
        self.player.pos.update(room.pixel_w // 2, room.pixel_h // 2)
        self.player.rect.center = (room.pixel_w // 2, room.pixel_h // 2)
        self.player_projectiles.empty()
        self.state = s.STATE_PLAYING
        play("door_open", 0.8)

    @property
    def biome_info(self) -> dict:
        return s.BIOMES[min(self.biome, len(s.BIOMES)) - 1]

    def _place_lost_bag(self):
        """Se la sacca persa è in questo piano, la rimette esattamente dove sei caduto."""
        bag = self.lost_bag
        if bag is None or bag["floor"] != self.floor or bag.get("biome", self.biome) != self.biome:
            return
        pos  = bag["room"] if bag["room"] in self.dungeon.grid else self.dungeon.start_pos
        room = self.dungeon.grid[pos]
        x, y = bag["pos"]
        item = Loot(x, y, "bag", bag["gold"])
        room.loot.add(item)
        self.dungeon.bag_pos = pos

    def _enter_dungeon_via_gate(self):
        """Gate: ritorna alla posizione esatta salvata al momento del recall."""
        if self.dungeon is None or self.recall_room_pos is None:
            return
        self.dungeon.current_pos = self.recall_room_pos
        play("recall", 0.8)
        self.dungeon.current_room.visited = True
        self.player.pos.x = float(self.recall_player_pos[0])
        self.player.pos.y = float(self.recall_player_pos[1])
        self.player.rect.center = (round(self.recall_player_pos[0]),
                                   round(self.recall_player_pos[1]))
        self.player_projectiles.empty()
        self.state = s.STATE_PLAYING

    def _advance_floor(self):
        """Genera il piano successivo senza tornare all'hub."""
        self.floor          += 1
        self._floor_complete = False
        self.dungeon         = self._new_dungeon()
        self._place_lost_bag()
        self.recall_room_pos   = None
        self.recall_player_pos = None
        self.hub.gate_active   = False
        self.player_projectiles.empty()
        room = self.dungeon.current_room
        self.player.pos.x = float(room.pixel_w // 2)
        self.player.pos.y = float(room.pixel_h // 2)
        self.player.rect.center = (room.pixel_w // 2, room.pixel_h // 2)
        self.state = s.STATE_PLAYING

    def _complete_biome(self):
        """Fine del bioma: preserva gli stat del player, torna all'hub, reset dungeon."""
        self.player.lose_audacia()
        self.biome           = min(self.biome + 1, len(s.BIOMES))   # si passa al bioma dopo
        self._mark_reached(self.biome, 1)
        self.dungeon         = None
        self.floor           = 1
        self._floor_complete = False
        self._pending_floor  = None
        self.recall_room_pos   = None
        self.recall_player_pos = None
        self.hub.gate_active   = False
        self.player_projectiles.empty()
        self.hub.enter_from_dungeon(self.player)
        self.state = s.STATE_HUB

    def _draw_floor_complete_overlay(self):
        name = self.biome_info["name"]
        if self.floor >= s.BOSCO_FLOORS:
            hud.modal(self.screen, f"{name} completato", "Hai attraversato tutti i piani",
                      [("confirm", "Torna all'hub")], accent=(190, 160, 255))
        else:
            hud.modal(self.screen, f"Piano {self.floor} completato", "Hai liberato tutte le stanze",
                      [("confirm", f"Piano {self.floor + 1}"), ("back", "Torna all'hub")],
                      extra=f"Proseguendo: +{s.AUDACIA_PER_FLOOR} Audacia")

    # ── Update ────────────────────────────────────────────────────────────────

    def _update(self, dt: float):
        # Bullet time: rallentano solo i nemici (game_dt); il gatto e i suoi colpi vanno a tempo pieno
        self.player._slow_timer = max(0.0, self.player._slow_timer - dt)
        game_dt = dt * 0.18 if self.player._slow_timer > 0 else dt

        room = self.dungeon.current_room
        if self._banner:
            self._banner[2] -= dt
            if self._banner[2] <= 0:
                self._banner = None

        # Mira: cursore del mouse, oppure stick destro col controller
        pad = InputManager.get()
        if pad.using_controller:
            aim = pad.aim_vector()
            if aim is not None:
                self.player.facing = aim
            elif pad.attack_held():
                self._aim_assist(room)
        else:
            cam          = room.get_camera_offset(self.player.pos)
            mx, my       = pygame.mouse.get_pos()
            world_mouse  = pygame.math.Vector2(mx + cam[0], my + cam[1])
            to_mouse     = world_mouse - self.player.pos
            if to_mouse.length_squared() > 1:
                self.player.facing = to_mouse.normalize()

        # Melee (click sinistro, X o grilletto destro — cooldown interno al player)
        if pad.attack_held() or self.player.attack_buffered:
            hitbox = self.player.try_attack()
            if hitbox:
                base = s.PLAYER_MELEE_DAMAGE + self.player.melee_damage_bonus
                crit = self.player._crit_armed
                if crit:
                    base *= 4 if self.player.audacia >= s.AUDACIA_TIER_FURY else 3
                    self.player._crit_armed = False
                    play("claw_swipe_crit")
                else:
                    play("claw_swipe", 0.7)
                room.apply_melee(hitbox, base, self.player)
                if crit and equipment.has(self.player, "claws_obsidian"):
                    room.shockwave(hitbox.centerx, hitbox.centery, base, self.player)

        # I nemici sono solidi: puoi farti chiudere. Schivata e balzo li attraversano;
        # chi ti è già addosso non blocca, così puoi sempre allontanarti.
        blockers = room.wall_rects
        if not (self.player.is_dodging or self.player.is_leaping):
            blockers = room.wall_rects + [e.rect for e in room.enemies
                                          if not e.rect.colliderect(self.player.rect)]
        self.player.update(dt, blockers)
        spells.update_player(self.player, dt, room.wall_rects, list(room.enemies))
        decoy = self.player.decoy
        if decoy is not None:                                  # l'ombra assorbe i proiettili
            for proj in list(room.enemy_projectiles):
                if proj.rect.colliderect(decoy.rect):
                    proj.kill()
                    decoy.take_damage(proj.damage)
        self.player_projectiles.update(dt, room.wall_rects)
        room.update(game_dt, self.player, self.player_projectiles)
        self._track_progress(room)
        if room.bag_recovered:                                  # sacca ripresa: niente più da recuperare
            room.bag_recovered = False
            self.lost_bag = None

        # Artiglio: applica danno al nemico marcato quando il balzo completa
        if self.player._claw_pending:
            self.player._claw_pending = False
            marked = self.player._marked_enemy
            if marked and marked.alive:
                room.apply_single_damage(marked, s.SPELL_CLAW_DAMAGE, self.player)
            self.player._spell_phase    = "ready"
            self.player._marked_enemy   = None
            self.player._leap_timer     = 0.0
            self.player._spell_cooldown = s.SPELL_SHOT_COOLDOWN

        direction = self.dungeon.try_transition(self.player)
        if direction:
            self.player_projectiles.empty()
            self.player.decoy = None                           # l'ombra resta nella stanza vecchia
            self.player._invincible_timer = max(self.player._invincible_timer, 0.6)
            # Interrompe il balzo se si cambia stanza
            if self.player._spell_phase == "leaping":
                self.player._spell_phase    = "ready"
                self.player._marked_enemy   = None
                self.player._spell_cooldown = s.SPELL_SHOT_COOLDOWN

        if (not self._floor_complete
                and self.dungeon.all_rooms_cleared):
            self._floor_complete = True
            self.state = s.STATE_FLOOR_COMPLETE
            if s.DEMO_LAST_FLOOR is not None and self.biome == 1 and self.floor >= s.DEMO_LAST_FLOOR:
                self.state = s.STATE_DEMO_END              # demo: il piano 2 non c'è ancora
            play("floor_complete")

        if not self.player.alive:
            self.state = s.STATE_DEAD
            play("player_death")
            p = self.player
            self.kept_gear = equipment.snapshot(p)       # l'equipaggiamento non si perde
            # la sacca resta nel piano dove sei caduto (una nuova sostituisce quella vecchia)
            self.lost_bag = ({"biome": self.biome, "floor": self.floor, "room": self.dungeon.current_pos,
                              "pos": (round(p.pos.x), round(p.pos.y)), "gold": p.gold}
                             if p.gold > 0 else None)

    # ── Draw ──────────────────────────────────────────────────────────────────

    def _draw(self):
        room = self.dungeon.current_room
        cam  = room.get_camera_offset(self.player.pos)

        self.screen.fill((12, 10, 16))
        room.draw(self.screen, cam, self.player, self.player_projectiles)
        spells.draw_player_fx(self.screen, self.player, cam)

        # Mark sul nemico bersaglio
        if self.player._spell_phase in ("marked_ready", "leaping"):
            enemy = self.player._marked_enemy
            if enemy and enemy.alive:
                ex = round(enemy.pos.x) - cam[0]
                ey = round(enemy.pos.y) - cam[1]
                t  = pygame.time.get_ticks() / 1000.0
                mr = int(18 + 4 * math.sin(t * 8.0))
                pygame.draw.circle(self.screen, (255, 130, 200), (ex, ey), mr, 2)      # segno del gomitolo
                pygame.draw.circle(self.screen, (255, 200, 230), (ex, ey), mr // 2, 2)

        self._draw_darkness(room, cam)

        # Lampo bianco-azzurro della schivata perfetta
        if self.player.flash_timer > 0:
            flash = gfx.Surface((s.SCREEN_W, s.SCREEN_H), pygame.SRCALPHA)
            flash.fill((200, 245, 255, round(110 * self.player.flash_timer / s.PERFECT_FLASH_TIME)))
            self.screen.blit(flash, (0, 0))

        # Vignette ciano durante il bullet time
        if self.player._slow_timer > 0:
            self.screen.blit(self._bt_vignette, (0, 0))

        self._draw_hud()

    def _draw_darkness(self, room, cam):
        """Dungeon al buio: si vede bene solo vicino al gatto e alle torce."""
        assets = AssetManager.get()
        if getattr(self, "_dark_layer", None) is None:
            self._dark_layer = gfx.Surface((s.SCREEN_W, s.SCREEN_H), pygame.SRCALPHA)
        dark = self._dark_layer
        sight = self.player.dark_sight_timer > 0
        darkness = round(self.biome_info["darkness"] * us.BRIGHTNESS_DARK[us.get("brightness")])
        cat_eye  = equipment.has(self.player, "amulet_cateye")
        if cat_eye:
            darkness = round(darkness * s.CATEYE_DARK_MULT)
        dark.fill((6, 5, 12, 70 if sight else darkness))
        px, py = round(self.player.pos.x) - cam[0], round(self.player.pos.y) - cam[1]
        lights = [(px, py, s.LIGHT_RADIUS)]
        if sight or cat_eye:
            lights += [(round(e.pos.x) - cam[0], round(e.pos.y) - cam[1] - 10, 60 if sight else 46) for e in room.enemies]
        if self.player.decoy is not None:                      # l'Ombra Felina si vede anche al buio
            lights.append((round(self.player.decoy.pos.x) - cam[0], round(self.player.decoy.pos.y) - cam[1], 80))
        t = pygame.time.get_ticks() / 1000.0
        for i, (x, y, r) in enumerate(room.light_sources()):
            flick = 1.0 + 0.05 * math.sin(t * 9 + i * 1.7) * math.sin(t * 4.3 + i)
            lights.append((x - cam[0], y - cam[1], round(r * flick / 4) * 4))   # raggi a passi: cache piccola
        for x, y, r in lights:
            if -r < x < s.SCREEN_W + r and -r < y < s.SCREEN_H + r:
                dark.blit(assets.light_hole(r), (x - r, y - r), special_flags=pygame.BLEND_RGBA_MIN)
        self.screen.blit(dark, (0, 0))
        if s.PLAYER_GLOW > 0:                                  # luce calda attorno al gatto
            glow = assets.warm_light(150, s.PLAYER_GLOW)
            self.screen.blit(glow, (px - 150, py - 150), special_flags=pygame.BLEND_RGB_ADD)

    def _draw_hud(self):
        room = self.dungeon.current_room
        hud.draw_status(self.screen, self.player)
        boss = next((e for e in room.enemies if isinstance(e, TopoArmaturato) and e.alive), None)
        if boss is not None and room.room_type == s.ROOM_TYPE_BOSS:
            hud.draw_boss_bar(self.screen, boss, "Topo Armaturato")
        if self._banner:
            hud.draw_banner(self.screen, *self._banner)
        hud.draw_notice(self.screen, self.player.notice)
        self._draw_fps()
        # comandi nella fascia nera a sinistra della stanza
        controls_panel.draw(self.screen, (s.SCREEN_W - room.pixel_w) // 2, 196)

    @staticmethod
    def _lbl(keyboard: str, pad: str) -> str:
        """Comandi da mostrare: tastiera/mouse o controller (con i simboli giusti)."""
        return InputManager.get().label(keyboard, pad)

    @staticmethod
    def _audio_hint() -> str:
        return "M Muto" if SoundManager.get().muted else "M Audio"

    def _draw_dungeon_confirm(self):
        current = (self.biome, self.floor) if (self.dungeon is not None and not self.dungeon.all_rooms_cleared) else None
        hud.draw_floor_select(self.screen, self.progress["reached"], self.progress["merchants"],
                              self._floor_sel, current)

    def _draw_map_overlay(self):
        SCALE = 5

        map_w = s.DUNGEON_COLS * s.ROOM_COLS * SCALE
        map_h = s.DUNGEON_ROWS * s.ROOM_ROWS * SCALE
        ox    = (s.SCREEN_W - map_w) // 2
        oy    = (s.SCREEN_H - map_h) // 2

        overlay = gfx.Surface((map_w, map_h), pygame.SRCALPHA)
        d       = self.dungeon

        for pos, room in d.grid.items():
            if not room.visited:
                continue
            col, row   = pos
            # stanze più piccole (boss) centrate sulle porte, come nel gioco
            off_c, off_r = s.ROOM_COLS // 2 - room.cols // 2, s.ROOM_ROWS // 2 - room.rows // 2
            base_x     = col * s.ROOM_COLS * SCALE + off_c * SCALE
            base_y     = row * s.ROOM_ROWS * SCALE + off_r * SCALE
            is_current = (pos == d.current_pos)

            fill  = (255, 255, 255, 12) if is_current else (100, 95, 130, 30)
            edge  = (240, 240, 245, 215) if is_current else (155, 150, 185, 170)
            tiles = room.tiles

            def is_wall(r2, c2, _t=tiles, _rows=room.rows, _cols=room.cols):
                if r2 < 0 or r2 >= _rows or c2 < 0 or c2 >= _cols:
                    return False                  # oltre il bordo c'è solo la porta: passaggio aperto
                return _t[r2][c2] != TILE_FLOOR

            for tr in range(room.rows):
                for tc in range(room.cols):
                    if tiles[tr][tc] != TILE_FLOOR:
                        continue
                    px = base_x + tc * SCALE
                    py = base_y + tr * SCALE
                    pygame.draw.rect(overlay, fill, (px, py, SCALE, SCALE))
                    if is_wall(tr - 1, tc):           # bordi continui (fino al tile dopo)
                        pygame.draw.line(overlay, edge, (px, py), (px + SCALE, py))
                    if is_wall(tr + 1, tc):
                        pygame.draw.line(overlay, edge, (px, py + SCALE - 1), (px + SCALE, py + SCALE - 1))
                    if is_wall(tr, tc - 1):
                        pygame.draw.line(overlay, edge, (px, py), (px, py + SCALE))
                    if is_wall(tr, tc + 1):
                        pygame.draw.line(overlay, edge, (px + SCALE - 1, py), (px + SCALE - 1, py + SCALE))

            # corridoio dalle porte della stanza piccola fino al bordo della sua cella
            mc, mr = room.cols // 2, room.rows // 2
            for door, is_open in room.doors.items():
                if not is_open:
                    continue
                if door in ("N", "S"):
                    n   = off_r
                    x0  = base_x + (mc - 1) * SCALE
                    y0  = base_y - n * SCALE if door == "N" else base_y + room.rows * SCALE
                    w, h = 2 * SCALE, n * SCALE
                    sides = [((x0, y0), (x0, y0 + h)), ((x0 + w - 1, y0), (x0 + w - 1, y0 + h))]
                else:
                    n   = off_c
                    y0  = base_y + (mr - 1) * SCALE
                    x0  = base_x - n * SCALE if door == "W" else base_x + room.cols * SCALE
                    w, h = n * SCALE, 2 * SCALE
                    sides = [((x0, y0), (x0 + w, y0)), ((x0, y0 + h - 1), (x0 + w, y0 + h - 1))]
                if n > 0:
                    pygame.draw.rect(overlay, fill, (x0, y0, w, h))
                    for a, b in sides:
                        pygame.draw.line(overlay, edge, a, b)

            if room.has_chest and not room.chest_opened:
                cx = base_x + (s.ROOM_COLS * SCALE) // 2
                cy = base_y + (s.ROOM_ROWS * SCALE) // 2
                pygame.draw.circle(overlay, (230, 190, 55, 180), (cx, cy), 4)

        col, row = d.current_pos                               # il gatto: pallino che si muove con te
        p   = self.player
        cur = d.current_room
        px = (col * s.ROOM_COLS + s.ROOM_COLS // 2 - cur.cols // 2) * SCALE + round(p.pos.x / s.TILE_SIZE * SCALE)
        py = (row * s.ROOM_ROWS + s.ROOM_ROWS // 2 - cur.rows // 2) * SCALE + round(p.pos.y / s.TILE_SIZE * SCALE)
        glow = 7 + round(2 * math.sin(pygame.time.get_ticks() / 1000.0 * 6))
        pygame.draw.circle(overlay, (120, 230, 255, 70), (px, py), glow)
        pygame.draw.circle(overlay, (20, 20, 30, 255), (px, py), 5)
        pygame.draw.circle(overlay, (120, 230, 255, 255), (px, py), 4)

        mpos = getattr(d, "merchant_pos", None)               # il mercante: solo dopo averlo trovato
        if mpos is not None and (d.grid[mpos].merchant.revealed or getattr(d, "merchant_known", False)):
            cx = mpos[0] * s.ROOM_COLS * SCALE + (s.ROOM_COLS * SCALE) // 2
            cy = mpos[1] * s.ROOM_ROWS * SCALE + (s.ROOM_ROWS * SCALE) // 2
            hud.merchant_icon(overlay, cx, cy, 8)

        bag_pos = getattr(d, "bag_pos", None)                 # la sacca si vede sempre sulla mappa
        if bag_pos is not None and any(i.loot_type == "bag" for i in d.grid[bag_pos].loot):
            t  = pygame.time.get_ticks() / 1000.0
            cx = bag_pos[0] * s.ROOM_COLS * SCALE + (s.ROOM_COLS * SCALE) // 2
            cy = bag_pos[1] * s.ROOM_ROWS * SCALE + (s.ROOM_ROWS * SCALE) // 2
            pygame.draw.circle(overlay, (250, 200, 60, 230), (cx, cy), 5 + round(2 * math.sin(t * 5)))
            pygame.draw.circle(overlay, (120, 80, 40, 255), (cx, cy), 3)
        self.screen.blit(overlay, (ox, oy))

        from game.menu import _font, _spaced
        title = _font(26, "title").render(self.biome_info["name"], True, (235, 232, 245))
        sub   = _spaced(f"PIANO {self.floor}", _font(12, "bold"), (255, 184, 92), 4)
        self.screen.blit(title, title.get_rect(centerx=s.SCREEN_W // 2, bottom=oy - 22))
        self.screen.blit(sub, sub.get_rect(centerx=s.SCREEN_W // 2, bottom=oy - 6))

    # ── Salvataggio ───────────────────────────────────────────────────────────
    #
    # Automatico e unico (game/save.py): si salva a ogni cambio di stato, stanza o piano e
    # quando chiudi il gioco. Nel dungeon si riprende all'ingresso della stanza in cui eri
    # (che ricomincia da capo); la morte si salva subito, con la sacca a terra.

    _PLAYER_FIELDS = ("hp", "hp_max", "energy", "energy_max", "xp", "level", "gold", "melee_damage_bonus",
                      "upgrades", "potions", "hp_regen_bonus", "energy_regen_bonus", "spells_owned",
                      "spell_slots", "audacia", "equipment", "backpack", "speed_bonus")
    _IN_DUNGEON    = (s.STATE_PLAYING, s.STATE_PAUSE, s.STATE_MERCHANT, s.STATE_FLOOR_COMPLETE)

    def _where(self) -> str:
        """Lo stato "di sotto": col menu equipaggiamento aperto, dove l'hai aperto."""
        return self._inv_return if self.state == s.STATE_INVENTORY else self.state

    def _autosave_signature(self) -> tuple:
        d = self.dungeon
        return (self.state, self.biome, self.floor, self._pending_floor, id(d),
                d.current_pos if d else None, self.lost_bag is None)

    def _start_slot(self, slot: int):
        """Dal menu: carica lo slot, o comincia una partita nuova se è vuoto."""
        self.slot     = slot
        self.lost_bag = None
        self.kept_gear = None
        self.progress = self._new_progress()
        self.run_seed = random.randrange(1 << 30)
        self._init_session()
        self._load_save()
        self._save_sig = self._autosave_signature()
        self._fade     = 0.6
        play("door_open", 0.6)

    def _to_menu(self):
        """Salva e torna al menu principale."""
        if self.slot is not None:
            self._save()
        self.slot  = None
        self.state = s.STATE_MENU
        self.menu._go("title")
        self._save_sig = self._autosave_signature()

    def _autosave(self):
        if self.slot is None or self.state == s.STATE_MENU:
            return
        sig = self._autosave_signature()
        if sig != self._save_sig:
            self._save_sig = sig
            self._save()

    def _save(self):
        if self.slot is None or self.state == s.STATE_MENU:
            return
        if self.state == s.STATE_DEMO_END:          # demo finita: la prossima volta si ricomincia
            save.delete(self.slot)
            return
        meta = {"run_seed": self.run_seed, "lost_bag": self.lost_bag, "progress": self.progress}
        if self.state == s.STATE_DEAD:              # morto: al prossimo avvio partita nuova (sacca a terra)
            save.write(self.slot, {"meta": {**meta, "gear": self.kept_gear}, "player": None,
                                   "saved_at": time.time()})
            return
        p = self.player
        data = {
            "meta": meta,
            "player": {k: getattr(p, k) for k in self._PLAYER_FIELDS},
            "session": {
                "biome": self.biome, "floor": self.floor, "pending_floor": self._pending_floor,
                "location": "dungeon" if self._where() in self._IN_DUNGEON and self.dungeon else "hub",
                "gate_active": self.hub.gate_active,
                "recall_room": self.recall_room_pos, "recall_pos": self.recall_player_pos,
            },
            "dungeon": None,
            "saved_at": time.time(),
        }
        d = self.dungeon
        if d is not None:
            data["dungeon"] = {
                "current": d.current_pos, "entry": d.entry_dir,
                "rooms": [[pos[0], pos[1], r.visited, r.cleared, r.chest_opened,
                           [r.merchant.revealed, sorted(r.merchant.sold)] if r.merchant else None]
                          for pos, r in d.grid.items()],
            }
        save.write(self.slot, data)

    def _load_save(self):
        data = save.read(self.slot)
        if not data:
            return
        meta = data.get("meta") or {}
        self.run_seed = meta.get("run_seed", self.run_seed)
        prog = meta.get("progress")
        if prog:
            self.progress = {**self._new_progress(), **prog}
        bag = meta.get("lost_bag")
        if bag:
            bag["room"], bag["pos"] = tuple(bag["room"]), tuple(bag["pos"])
        self.lost_bag = bag
        pdata = data.get("player")
        if not pdata:                               # l'ultima volta sei morto: partita nuova
            self.kept_gear = meta.get("gear")        # ma l'equipaggiamento resta
            equipment.restore(self.player, self.kept_gear)
            return
        p = self.player
        for k in self._PLAYER_FIELDS:
            if k in pdata:
                setattr(p, k, pdata[k])
        sess = data.get("session") or {}
        self.biome          = sess.get("biome", self.biome)
        self.floor          = sess.get("floor", 1)
        self._pending_floor = sess.get("pending_floor")
        self.hub.gate_active = sess.get("gate_active", False)
        rr = sess.get("recall_room")
        self.recall_room_pos   = tuple(rr) if rr else None
        self.recall_player_pos = tuple(sess["recall_pos"]) if sess.get("recall_pos") else None

        dd = data.get("dungeon")
        if dd:                                      # stesso seme = stesso piano: poi si rimette com'era
            self.dungeon = self._new_dungeon()
            self._place_lost_bag()
            for c, r, visited, cleared, chest, merch in dd.get("rooms", []):
                room = self.dungeon.grid.get((c, r))
                if room is None:
                    continue
                room.visited, room.chest_opened = visited, chest
                if cleared:
                    room.cleared = True
                    room.enemies.empty()
                if merch and room.merchant is not None:
                    room.merchant.revealed = merch[0]
                    room.merchant.sold     = set(merch[1])
            cur = tuple(dd.get("current") or self.dungeon.start_pos)
            if cur in self.dungeon.grid:
                self.dungeon.current_pos = cur
            self.dungeon.entry_dir = dd.get("entry")
            self._floor_complete   = self.dungeon.all_rooms_cleared

        if sess.get("location") == "dungeon" and self.dungeon is not None:
            self.dungeon.current_room.enter(p, self.dungeon.entry_dir)   # all'ingresso della stanza
            self.state = s.STATE_PLAYING
        else:
            self.hub.enter(p)
            self.state = s.STATE_HUB

    # ── Restart ───────────────────────────────────────────────────────────────

    def _restart(self):
        self._init_session()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    game = Game()
    try:
        game.run()
    except Exception:
        game._save()                                # anche se il gioco va in crash
        raise
