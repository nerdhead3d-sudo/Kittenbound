import math
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
from game.sound import SoundManager, play
from game.input import InputManager
from game import gfx
from game import spells


class Game:
    """Nucleo del gioco: loop principale e gestione stati."""

    def __init__(self):
        pygame.mixer.pre_init(44100, -16, 2, 512)   # buffer piccolo: suoni senza ritardo
        pygame.init()
        pygame.display.set_caption(s.TITLE)

        self.fullscreen = s.FULLSCREEN
        gfx.setup((s.SCREEN_W, s.SCREEN_H))          # HD: K = 2 su schermi 2560x1440
        self._set_display()
        self.clock   = pygame.time.Clock()
        self.running = True

        assets = AssetManager.get()
        self.font_large = assets.font(48, bold=True)
        self.font_small = assets.font(22)
        self.font_tiny  = assets.font(16)

        self._init_session()
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
        self.player_projectiles = pygame.sprite.Group()

        self.player = Player(float(s.SCREEN_W // 2), float(s.SCREEN_H // 2))
        self.hub.enter(self.player)

        self.recall_room_pos   = None   # (col,row) salvata al G recall
        self.recall_player_pos = None   # (x,y) world salvata al G recall

        self.floor               = 1     # piano corrente del bioma (1-BOSCO_FLOORS)
        self._floor_complete     = False  # True dopo che all_rooms_cleared scatta
        self._pending_floor      = None  # piano da caricare al prossimo ingresso dall'hub

        self.state    = s.STATE_HUB
        self.show_map = False

    # ── Loop ──────────────────────────────────────────────────────────────────

    def _draw_stat_bar(self, y: int, pct: float, color: tuple, label: str,
                       bx: int = 14, bw: int = 180, bh: int = 14):
        pygame.draw.rect(self.screen, s.C_BAR_BG, (bx, y, bw, bh), border_radius=3)
        if pct > 0:
            pygame.draw.rect(self.screen, color,
                             (bx, y, int(bw * pct), bh), border_radius=3)
        pygame.draw.rect(self.screen, s.C_TEXT, (bx, y, bw, bh), 1, border_radius=3)
        self.screen.blit(self.font_tiny.render(label, True, s.C_TEXT),
                         (bx + bw + 6, y))

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

            self._handle_events()

            if self.state == s.STATE_HUB:
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
            elif self.state == s.STATE_DEAD:
                self._draw()
                self._draw_overlay("Sei morto!", self._lbl("(R) Riprova   (ESC) Esci", "({A}) Riprova"),
                                   (180, 50, 50))
            elif self.state == s.STATE_PAUSE:
                self._draw()
                self._draw_overlay("Pausa", self._lbl("(P) Continua   (ESC) Esci", "({START}) Continua"),
                                   (80, 80, 150))

            if self.show_map and self.state == s.STATE_PLAYING:
                self._draw_map_overlay()

            pygame.display.flip()

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

    def _pad_key(self, action: str) -> "int | None":
        """Traduce un pulsante del controller nel tasto equivalente per lo stato attuale."""
        st = self.state
        if st == s.STATE_PLAYING:
            return {"confirm": pygame.K_SPACE, "dodge": pygame.K_SPACE, "back": pygame.K_q,
                    "spell": pygame.K_f, "recall": pygame.K_r, "down": pygame.K_g, "map": pygame.K_TAB,
                    "parry": pygame.K_LSHIFT,
                    "pause": pygame.K_ESCAPE}.get(action)
        if st == s.STATE_PAUSE:
            return pygame.K_p if action in ("pause", "confirm") else None
        if st == s.STATE_DEAD:
            return pygame.K_r if action == "confirm" else None
        if st == s.STATE_HUB:
            return pygame.K_e if action == "confirm" else None      # B nell'hub non chiude il gioco
        if st == s.STATE_VENDOR:
            return {"confirm": pygame.K_RETURN, "back": pygame.K_ESCAPE, "attack": pygame.K_r,
                    "up": pygame.K_UP, "down": pygame.K_DOWN}.get(action)
        if st in (s.STATE_DUNGEON_CONFIRM, s.STATE_FLOOR_COMPLETE):
            return {"confirm": pygame.K_RETURN, "back": pygame.K_ESCAPE}.get(action)
        return None

    def _on_key(self, key: int, mod: int = 0):
        """Azione di un tasto (o di un pulsante del controller già tradotto)."""
        alt_enter = key == pygame.K_RETURN and mod & pygame.KMOD_ALT
        if key == pygame.K_F11 or alt_enter:
            self.fullscreen = not self.fullscreen
            self._set_display()
            return
        if key == pygame.K_m:
            SoundManager.get().toggle_mute()
            return
        # Il vendor intercetta tutti i tasti
        if self.state == s.STATE_VENDOR:
            if self.vendor_ui.handle_key(key, self.player):
                play("ui_open", 0.6)
                self.state = s.STATE_HUB

        elif self.state == s.STATE_FLOOR_COMPLETE:
            if key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.floor < s.BOSCO_FLOORS:
                    self._advance_floor()
                else:
                    self._complete_biome()
            elif key in (pygame.K_ESCAPE, pygame.K_g):
                if self.floor < s.BOSCO_FLOORS:
                    self._pending_floor = self.floor + 1
                self._floor_complete   = False
                self.recall_room_pos   = None
                self.recall_player_pos = None
                self.hub.gate_active   = False
                self.player_projectiles.empty()
                self.hub.enter_from_dungeon(self.player)
                self.state = s.STATE_HUB

        elif self.state == s.STATE_DUNGEON_CONFIRM:
            if key in (pygame.K_RETURN, pygame.K_SPACE):
                self._enter_dungeon_via_entrance()
            elif key == pygame.K_ESCAPE:
                self.state = s.STATE_HUB

        elif key == pygame.K_ESCAPE:
            if self.state == s.STATE_PLAYING:
                self.state    = s.STATE_PAUSE
                self.show_map = False
            else:
                self.running = False

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
        p  = self.player
        by = 14

        self._draw_stat_bar(by,      p.hp_pct,     s.C_HP_BAR,     f"HP {int(p.hp)}/{p.hp_max}")
        self._draw_stat_bar(by + 20, p.energy_pct, s.C_ENERGY_BAR, f"EN {int(p.energy)}/{p.energy_max}")
        self._draw_stat_bar(by + 40, p.xp_pct,     s.C_XP_BAR,     f"LV {p.level}")

        self.screen.blit(
            self.font_tiny.render(f"Oro: {p.gold}", True, s.C_COIN),
            (14, by + 62))

        self._draw_potions(14, by + 84)

        self.screen.blit(
            self.font_tiny.render(f"FPS {self.clock.get_fps():.0f}", True, s.C_TEXT),
            (s.SCREEN_W - 65, 8))

        hint = AssetManager.get().ui_font(16).render(self._lbl(
            f"WASD Muovi  |  E Interagisci  |  {self._audio_hint()}",
            "{LS} Muovi  |  {A} Interagisci"), True, (100, 95, 90))
        self.screen.blit(hint, (10, s.SCREEN_H - 20))

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

    def _draw_potions(self, x: int, y: int):
        """Boccette di pozione: piene (rosse) quante ne hai, vuote fino alla capienza."""
        for i in range(s.POTION_MAX):
            bx   = x + i * 16
            full = i < self.player.potions
            body = (200, 40, 50) if full else (55, 50, 58)
            pygame.draw.rect(self.screen, (150, 130, 110) if full else (70, 66, 72), (bx + 4, y, 5, 4))  # tappo
            pygame.draw.circle(self.screen, body, (bx + 6, y + 10), 6)
            pygame.draw.circle(self.screen, (230, 225, 220) if full else (90, 86, 94), (bx + 6, y + 10), 6, 1)
            if full:
                pygame.draw.circle(self.screen, (255, 170, 160), (bx + 4, y + 8), 2)
        self.screen.blit(self.font_tiny.render("Q", True, (160, 155, 150)),
                         (x + s.POTION_MAX * 16 + 4, y + 2))

    def _enter_dungeon_via_entrance(self):
        """Entrata: piano pendente, nuova run da piano 1, o rientro nel dungeon corrente."""
        if self._pending_floor is not None:
            self.floor           = self._pending_floor
            self._pending_floor  = None
            self._floor_complete = False
            self.dungeon         = Dungeon(floor=self.floor)
            self.recall_room_pos   = None
            self.recall_player_pos = None
            self.hub.gate_active   = False
        elif self.dungeon is None or self.dungeon.all_rooms_cleared:
            self.floor           = 1
            self._floor_complete = False
            self.dungeon         = Dungeon(floor=1)
            self.recall_room_pos   = None
            self.recall_player_pos = None
            self.hub.gate_active   = False
        else:
            self.dungeon.current_pos = self.dungeon.start_pos
            self.dungeon.current_room.visited = True

        room = self.dungeon.current_room
        self.player.pos.x = float(room.pixel_w // 2)
        self.player.pos.y = float(room.pixel_h // 2)
        self.player.rect.center = (room.pixel_w // 2, room.pixel_h // 2)
        self.player_projectiles.empty()
        self.state = s.STATE_PLAYING
        play("door_open", 0.8)

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
        self.dungeon         = Dungeon(floor=self.floor)
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
        PW, PH = 500, 260
        px = (s.SCREEN_W - PW) // 2
        py = (s.SCREEN_H - PH) // 2

        bg = gfx.Surface((PW, PH), pygame.SRCALPHA)
        bg.fill((15, 13, 20, 235))
        self.screen.blit(bg, (px, py))

        is_biome_complete = (self.floor >= s.BOSCO_FLOORS)
        border_col = (130, 100, 200) if is_biome_complete else (70, 130, 90)
        pygame.draw.rect(self.screen, border_col, (px, py, PW, PH), 2, border_radius=6)

        if is_biome_complete:
            title_txt  = "BOSCO — Completato!"
            sub_txt    = "Hai attraversato tutti e 4 i piani del Bosco."
            yes_txt    = self._lbl("[INVIO / SPAZIO]  Torna all'Hub", "[{A}]  Torna all'Hub")
            back_txt   = self._lbl("[ESC / G]  Torna all'Hub", "[{B}]  Torna all'Hub")
            title_col  = (190, 160, 255)
        else:
            title_txt  = f"Bosco — Piano {self.floor}/{s.BOSCO_FLOORS} Completato!"
            sub_txt    = "Hai liberato tutte le stanze."
            yes_txt    = self._lbl(f"[INVIO / SPAZIO]  Piano {self.floor + 1}", f"[{{A}}]  Piano {self.floor + 1}")
            back_txt   = self._lbl("[ESC / G]  Torna all'Hub", "[{B}]  Torna all'Hub")
            title_col  = (160, 220, 170)

        title = self.font_small.render(title_txt, True, title_col)
        self.screen.blit(title, title.get_rect(centerx=px + PW // 2, top=py + 24))

        sub = self.font_tiny.render(sub_txt, True, (180, 175, 165))
        self.screen.blit(sub, sub.get_rect(centerx=px + PW // 2, top=py + 76))

        yes = AssetManager.get().ui_font(22).render(yes_txt, True, (140, 220, 140))
        self.screen.blit(yes, yes.get_rect(centerx=px + PW // 2, top=py + 138))

        no = AssetManager.get().ui_font(22).render(back_txt, True, (190, 130, 120))
        self.screen.blit(no, no.get_rect(centerx=px + PW // 2, top=py + 178))

    # ── Update ────────────────────────────────────────────────────────────────

    def _update(self, dt: float):
        # Bullet time: rallentano solo i nemici (game_dt); il gatto e i suoi colpi vanno a tempo pieno
        self.player._slow_timer = max(0.0, self.player._slow_timer - dt)
        game_dt = dt * 0.18 if self.player._slow_timer > 0 else dt

        room = self.dungeon.current_room

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
                if self.player._crit_armed:
                    base *= 3
                    self.player._crit_armed = False
                    play("claw_swipe_crit")
                else:
                    play("claw_swipe", 0.7)
                room.apply_melee(hitbox, base, self.player)

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
            play("floor_complete")

        if not self.player.alive:
            self.state = s.STATE_DEAD
            play("player_death")

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
                pygame.draw.circle(self.screen, (200, 240, 80), (ex, ey), mr, 2)
                pygame.draw.circle(self.screen, (240, 200, 50), (ex, ey), mr // 2, 2)

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
        dark.fill((6, 5, 12, 70 if sight else s.DARKNESS_ALPHA))
        px, py = round(self.player.pos.x) - cam[0], round(self.player.pos.y) - cam[1]
        lights = [(px, py, s.LIGHT_RADIUS)]
        if sight:
            lights += [(round(e.pos.x) - cam[0], round(e.pos.y) - cam[1] - 10, 60) for e in room.enemies]
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
        p    = self.player
        room = self.dungeon.current_room
        by   = 14

        self._draw_stat_bar(by,      p.hp_pct,     s.C_HP_BAR,     f"HP {int(p.hp)}/{p.hp_max}")
        self._draw_stat_bar(by + 20, p.energy_pct, s.C_ENERGY_BAR, f"EN {int(p.energy)}/{p.energy_max}")
        self._draw_stat_bar(by + 40, p.xp_pct,     s.C_XP_BAR,     f"LV {p.level}")

        ne = len(room.enemies)
        ec = s.C_DOOR_OPEN if ne == 0 else (200, 100, 80)
        self.screen.blit(
            self.font_tiny.render(
                "Stanza liberata!" if ne == 0 else f"Nemici: {ne}", True, ec),
            (14, by + 62))

        self.screen.blit(
            self.font_tiny.render(f"Oro: {p.gold}", True, s.C_COIN),
            (14, by + 80))

        self.screen.blit(
            self.font_tiny.render(
                f"Bosco  Piano {self.floor}/{s.BOSCO_FLOORS}", True, (140, 190, 230)),
            (14, by + 98))

        self._draw_potions(14, by + 120)
        self._draw_spell_slots(14, by + 144)

        self.screen.blit(
            self.font_tiny.render(f"FPS {self.clock.get_fps():.0f}", True, s.C_TEXT),
            (s.SCREEN_W - 65, 8))

        if room._locked:
            lock_txt = self.font_small.render("STANZA BLOCCATA", True, s.C_DOOR_LOCKED)
            self.screen.blit(lock_txt,
                             lock_txt.get_rect(centerx=s.SCREEN_W // 2, top=14))

        if (room.room_type == s.ROOM_TYPE_BOSS and not room.cleared
                and len(room.enemies) > 0):
            boss_lbl = self.font_small.render("TOPO ARMATURATO", True, (178, 145, 210))
            self.screen.blit(boss_lbl,
                             boss_lbl.get_rect(centerx=s.SCREEN_W // 2, bottom=s.SCREEN_H - 54))

        cd = f" CD {p._spell_cooldown:.0f}s" if p._spell_cooldown > 0 else ""
        hint_str = self._lbl(
            f"WASD  |  Click Attacca  |  Space Schiva  |  Shift/Dx Para  |  F/R Magie{cd}  |  Q Pozione  |  TAB Mappa  |  G Hub  |  "
            f"ESC Pausa  |  {self._audio_hint()}",
            f"{{RS}} Mira  |  {{X}}/{{RT}} Attacca  |  {{A}}/{{LT}} Schiva  |  {{RB}} Para  |  {{Y}}/{{LB}} Magie{cd}  |  {{B}} Pozione  |  "
            f"{{VIEW}} Mappa  |  Croce giù Hub  |  {{START}} Pausa")
        self.screen.blit(
            AssetManager.get().ui_font(16).render(hint_str, True, (100, 95, 90)),
            (10, s.SCREEN_H - 20))

    def _draw_spell_slots(self, x: int, y: int):
        """Le 2 magie equipaggiate: tasto, nome, costo (grigie se manca l'energia)."""
        p = self.player
        for i, spell_id in enumerate(p.spell_slots):
            key = self._lbl("F" if i == 0 else "R", "{Y}" if i == 0 else "{LB}")
            if spell_id is None:
                txt, col = f"{key}  —", (90, 86, 94)
            else:
                sp  = spells.SPELLS[spell_id]
                ok  = p.energy >= sp.cost
                txt = f"{key}  {sp.name}  {sp.cost}"
                col = sp.color if ok else (95, 92, 100)
            self.screen.blit(AssetManager.get().ui_font(15).render(txt, True, col), (x, y + i * 18))

    @staticmethod
    def _lbl(keyboard: str, pad: str) -> str:
        """Comandi da mostrare: tastiera/mouse o controller (con i simboli giusti)."""
        return InputManager.get().label(keyboard, pad)

    @staticmethod
    def _audio_hint() -> str:
        return "M Muto" if SoundManager.get().muted else "M Audio"

    def _draw_dungeon_confirm(self):
        PW, PH = 440, 230
        px = (s.SCREEN_W - PW) // 2
        py = (s.SCREEN_H - PH) // 2

        bg = gfx.Surface((PW, PH), pygame.SRCALPHA)
        bg.fill((15, 13, 20, 235))
        self.screen.blit(bg, (px, py))
        pygame.draw.rect(self.screen, (70, 130, 90), (px, py, PW, PH), 2, border_radius=6)

        if self._pending_floor is not None:
            title_txt = f"BOSCO — PIANO {self._pending_floor}/{s.BOSCO_FLOORS}"
        else:
            title_txt = f"BOSCO — PIANO {self.floor}/{s.BOSCO_FLOORS}"
        title = self.font_small.render(title_txt, True, (160, 220, 170))
        self.screen.blit(title, title.get_rect(centerx=px + PW // 2, top=py + 16))

        if self._pending_floor is not None:
            q = f"Continua al Piano {self._pending_floor}?"
        elif self.dungeon is not None and not self.dungeon.all_rooms_cleared:
            q = f"Vuoi rientrare al Piano {self.floor}?"
        else:
            q = "Sei pronto ad avventurarti nel Bosco?"
        q_surf = self.font_small.render(q, True, (210, 205, 195))
        self.screen.blit(q_surf, q_surf.get_rect(centerx=px + PW // 2, top=py + 66))

        font = AssetManager.get().ui_font(22)
        yes = font.render(self._lbl("[INVIO / SPAZIO]  Avanti!", "[{A}]  Avanti!"), True, (140, 220, 140))
        no  = font.render(self._lbl("[ESC]  Aspetta ancora", "[{B}]  Aspetta ancora"), True, (190, 130, 120))
        self.screen.blit(yes, yes.get_rect(centerx=px + PW // 2, top=py + 128))
        self.screen.blit(no,  no.get_rect(centerx=px + PW // 2, top=py + 166))

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
            base_x     = col * s.ROOM_COLS * SCALE
            base_y     = row * s.ROOM_ROWS * SCALE
            is_current = (pos == d.current_pos)

            fill  = (255, 255, 255, 12) if is_current else (100, 95, 130, 30)
            edge  = (240, 240, 245, 215) if is_current else (155, 150, 185, 170)
            tiles = room.tiles

            def is_wall(r2, c2, _t=tiles, _rows=room.rows, _cols=room.cols):
                if r2 < 0 or r2 >= _rows or c2 < 0 or c2 >= _cols:
                    return True
                return _t[r2][c2] != TILE_FLOOR

            for tr in range(room.rows):
                for tc in range(room.cols):
                    if tiles[tr][tc] != TILE_FLOOR:
                        continue
                    px = base_x + tc * SCALE
                    py = base_y + tr * SCALE
                    pygame.draw.rect(overlay, fill, (px, py, SCALE, SCALE))
                    if is_wall(tr - 1, tc):
                        pygame.draw.line(overlay, edge, (px, py), (px + SCALE - 1, py))
                    if is_wall(tr + 1, tc):
                        pygame.draw.line(overlay, edge, (px, py + SCALE - 1), (px + SCALE - 1, py + SCALE - 1))
                    if is_wall(tr, tc - 1):
                        pygame.draw.line(overlay, edge, (px, py), (px, py + SCALE - 1))
                    if is_wall(tr, tc + 1):
                        pygame.draw.line(overlay, edge, (px + SCALE - 1, py), (px + SCALE - 1, py + SCALE - 1))

            if room.has_chest and not room.chest_opened:
                cx = base_x + (s.ROOM_COLS * SCALE) // 2
                cy = base_y + (s.ROOM_ROWS * SCALE) // 2
                pygame.draw.circle(overlay, (230, 190, 55, 180), (cx, cy), 4)

        self.screen.blit(overlay, (ox, oy))

        floor_surf = self.font_small.render(
            f"Bosco — Piano {self.floor}/{s.BOSCO_FLOORS}", True, (200, 195, 240))
        self.screen.blit(floor_surf,
                         floor_surf.get_rect(centerx=s.SCREEN_W // 2, bottom=oy - 8))

    def _draw_overlay(self, title: str, subtitle: str, color: tuple):
        overlay = gfx.Surface((s.SCREEN_W, s.SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        self.screen.blit(overlay, (0, 0))

        cx, cy = s.SCREEN_W // 2, s.SCREEN_H // 2
        t   = self.font_large.render(title, True, color)
        sub = AssetManager.get().ui_font(22).render(subtitle, True, s.C_TEXT)
        self.screen.blit(t,   t.get_rect(center=(cx, cy - 30)))
        self.screen.blit(sub, sub.get_rect(center=(cx, cy + 30)))

    # ── Restart ───────────────────────────────────────────────────────────────

    def _restart(self):
        self._init_session()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    Game().run()
