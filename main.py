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


class Game:
    """Nucleo del gioco: loop principale e gestione stati."""

    def __init__(self):
        pygame.init()
        pygame.display.set_caption(s.TITLE)

        self.screen  = pygame.display.set_mode((s.SCREEN_W, s.SCREEN_H))
        self.clock   = pygame.time.Clock()
        self.running = True

        assets = AssetManager.get()
        self.font_large = assets.font(48, bold=True)
        self.font_small = assets.font(22)
        self.font_tiny  = assets.font(16)

        self._init_session()
        self._bt_vignette = self._make_bt_vignette()

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
        vign = pygame.Surface((s.SCREEN_W, s.SCREEN_H), pygame.SRCALPHA)
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
                self._draw_overlay("Sei morto!", "(R) Riprova   (ESC) Esci", (180, 50, 50))
            elif self.state == s.STATE_PAUSE:
                self._draw()
                self._draw_overlay("Pausa", "(P) Continua   (ESC) Esci", (80, 80, 150))

            if self.show_map and self.state == s.STATE_PLAYING:
                self._draw_map_overlay()

            pygame.display.flip()

        pygame.quit()
        sys.exit()

    # ── Events ────────────────────────────────────────────────────────────────

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            elif event.type == pygame.KEYDOWN:
                # Il vendor intercetta tutti i tasti
                if self.state == s.STATE_VENDOR:
                    if self.vendor_ui.handle_key(event.key, self.player):
                        self.state = s.STATE_HUB

                elif self.state == s.STATE_FLOOR_COMPLETE:
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        if self.floor < s.BOSCO_FLOORS:
                            self._advance_floor()
                        else:
                            self._complete_biome()
                    elif event.key in (pygame.K_ESCAPE, pygame.K_g):
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
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self._enter_dungeon_via_entrance()
                    elif event.key == pygame.K_ESCAPE:
                        self.state = s.STATE_HUB

                elif event.key == pygame.K_ESCAPE:
                    if self.state == s.STATE_PLAYING:
                        self.state    = s.STATE_PAUSE
                        self.show_map = False
                    else:
                        self.running = False

                elif event.key == pygame.K_TAB:
                    if self.state == s.STATE_PLAYING:
                        self.show_map = not self.show_map

                elif event.key == pygame.K_p:
                    if self.state == s.STATE_PAUSE:
                        self.state = s.STATE_PLAYING

                elif event.key == pygame.K_r:
                    if self.state == s.STATE_DEAD:
                        self._restart()

                elif event.key == pygame.K_e:
                    if self.state == s.STATE_HUB:
                        interaction = self.hub.get_interaction(self.player.pos)
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

                elif event.key == pygame.K_SPACE:
                    if self.state == s.STATE_PLAYING:
                        keys = pygame.key.get_pressed()
                        vel = pygame.math.Vector2(
                            float(keys[pygame.K_d] - keys[pygame.K_a]),
                            float(keys[pygame.K_s] - keys[pygame.K_w]),
                        )
                        self.player.try_dodge(vel)

                elif event.key == pygame.K_f:
                    if self.state == s.STATE_PLAYING:
                        if self.player._spell_phase == "ready":
                            if self.player.try_cast_spell():
                                room = self.dungeon.current_room
                                cam  = room.get_camera_offset(self.player.pos)
                                mx, my = pygame.mouse.get_pos()
                                direction = pygame.math.Vector2(
                                    mx + cam[0] - self.player.pos.x,
                                    my + cam[1] - self.player.pos.y,
                                )
                                if direction.length_squared() > 0:
                                    self.player_projectiles.add(Projectile(
                                        self.player.pos.x, self.player.pos.y,
                                        direction,
                                        damage=s.SPELL_SHOT_DAMAGE,
                                        owner="player",
                                        speed=s.SPELL_SHOT_SPEED,
                                        max_range=500.0,
                                        is_spell=True,
                                    ))
                        elif self.player._spell_phase == "marked_ready":
                            self.player.try_leap()

                elif event.key == pygame.K_g:
                    if self.state == s.STATE_PLAYING and self.dungeon:
                        self.recall_room_pos   = self.dungeon.current_pos
                        self.recall_player_pos = (self.player.pos.x, self.player.pos.y)
                        self.hub.activate_gate()
                        self.player.cancel_spell()
                        self.player_projectiles.empty()
                        self.hub.enter_from_dungeon(self.player)
                        self.state = s.STATE_HUB

    # ── Hub ───────────────────────────────────────────────────────────────────

    def _update_hub(self, dt: float):
        self.player.update(dt, wall_rects=None)
        margin = float(s.PLAYER_RADIUS + 20)
        self.player.pos.x = max(margin, min(float(s.SCREEN_W) - margin, self.player.pos.x))
        self.player.pos.y = max(margin, min(float(s.SCREEN_H) - margin, self.player.pos.y))
        self.player.rect.center = (round(self.player.pos.x), round(self.player.pos.y))

    def _draw_hub(self):
        self.hub.draw(self.screen, self.player.pos)
        self.player.draw(self.screen)
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

        self.screen.blit(
            self.font_tiny.render(f"FPS {self.clock.get_fps():.0f}", True, s.C_TEXT),
            (s.SCREEN_W - 65, 8))

        hint = self.font_tiny.render(
            "WASD Muovi  |  E Interagisci", True, (100, 95, 90))
        self.screen.blit(hint, (10, s.SCREEN_H - 20))

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

    def _enter_dungeon_via_gate(self):
        """Gate: ritorna alla posizione esatta salvata al momento del recall."""
        if self.dungeon is None or self.recall_room_pos is None:
            return
        self.dungeon.current_pos = self.recall_room_pos
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

        bg = pygame.Surface((PW, PH), pygame.SRCALPHA)
        bg.fill((15, 13, 20, 235))
        self.screen.blit(bg, (px, py))

        is_biome_complete = (self.floor >= s.BOSCO_FLOORS)
        border_col = (130, 100, 200) if is_biome_complete else (70, 130, 90)
        pygame.draw.rect(self.screen, border_col, (px, py, PW, PH), 2, border_radius=6)

        if is_biome_complete:
            title_txt  = "BOSCO — Completato!"
            sub_txt    = "Hai attraversato tutti e 4 i piani del Bosco."
            yes_txt    = "[INVIO / SPAZIO]  Torna all'Hub"
            back_txt   = "[ESC / G]  Torna all'Hub"
            title_col  = (190, 160, 255)
        else:
            title_txt  = f"Bosco — Piano {self.floor}/{s.BOSCO_FLOORS} Completato!"
            sub_txt    = "Hai liberato tutte le stanze."
            yes_txt    = f"[INVIO / SPAZIO]  Piano {self.floor + 1}"
            back_txt   = "[ESC / G]  Torna all'Hub"
            title_col  = (160, 220, 170)

        title = self.font_small.render(title_txt, True, title_col)
        self.screen.blit(title, title.get_rect(centerx=px + PW // 2, top=py + 24))

        sub = self.font_tiny.render(sub_txt, True, (180, 175, 165))
        self.screen.blit(sub, sub.get_rect(centerx=px + PW // 2, top=py + 76))

        yes = self.font_small.render(yes_txt, True, (140, 220, 140))
        self.screen.blit(yes, yes.get_rect(centerx=px + PW // 2, top=py + 138))

        no = self.font_small.render(back_txt, True, (190, 130, 120))
        self.screen.blit(no, no.get_rect(centerx=px + PW // 2, top=py + 178))

    # ── Update ────────────────────────────────────────────────────────────────

    def _update(self, dt: float):
        # Bullet time: il timer scende in tempo reale, tutto il resto usa game_dt
        self.player._slow_timer = max(0.0, self.player._slow_timer - dt)
        game_dt = dt * 0.18 if self.player._slow_timer > 0 else dt

        room = self.dungeon.current_room

        # Aggiorna facing verso il cursore
        cam          = room.get_camera_offset(self.player.pos)
        mx, my       = pygame.mouse.get_pos()
        world_mouse  = pygame.math.Vector2(mx + cam[0], my + cam[1])
        to_mouse     = world_mouse - self.player.pos
        if to_mouse.length_squared() > 1:
            self.player.facing = to_mouse.normalize()

        # Melee (click sinistro — cooldown interno al player)
        if pygame.mouse.get_pressed()[0]:
            hitbox = self.player.try_attack()
            if hitbox:
                base = s.PLAYER_MELEE_DAMAGE + self.player.melee_damage_bonus
                if self.player._crit_armed:
                    base *= 3
                    self.player._crit_armed = False
                room.apply_melee(hitbox, base, self.player)

        self.player.update(game_dt, room.wall_rects)
        self.player_projectiles.update(game_dt, room.wall_rects)
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

        if not self.player.alive:
            self.state = s.STATE_DEAD

    # ── Draw ──────────────────────────────────────────────────────────────────

    def _draw(self):
        room = self.dungeon.current_room
        cam  = room.get_camera_offset(self.player.pos)

        self.screen.fill((12, 10, 16))
        room.draw(self.screen, cam)

        for proj in self.player_projectiles:
            proj.draw(self.screen, cam)

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

        self.player.draw(self.screen, cam)

        # Vignette ciano durante il bullet time
        if self.player._slow_timer > 0:
            self.screen.blit(self._bt_vignette, (0, 0))

        self._draw_hud()

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

        spell_hint = f"F Spell CD {p._spell_cooldown:.0f}s" if p._spell_cooldown > 0 else "F Spell"
        hint_str = f"WASD  |  Click Attacca  |  Space Schiva  |  {spell_hint}  |  TAB Mappa  |  G Hub  |  ESC Pausa"
        self.screen.blit(
            self.font_tiny.render(hint_str, True, (100, 95, 90)),
            (10, s.SCREEN_H - 20))

    def _draw_dungeon_confirm(self):
        PW, PH = 440, 230
        px = (s.SCREEN_W - PW) // 2
        py = (s.SCREEN_H - PH) // 2

        bg = pygame.Surface((PW, PH), pygame.SRCALPHA)
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

        yes = self.font_small.render("[INVIO / SPAZIO]  Avanti!", True, (140, 220, 140))
        no  = self.font_small.render("[ESC]  Aspetta ancora", True, (190, 130, 120))
        self.screen.blit(yes, yes.get_rect(centerx=px + PW // 2, top=py + 128))
        self.screen.blit(no,  no.get_rect(centerx=px + PW // 2, top=py + 166))

    def _draw_map_overlay(self):
        SCALE = 5

        map_w = s.DUNGEON_COLS * s.ROOM_COLS * SCALE
        map_h = s.DUNGEON_ROWS * s.ROOM_ROWS * SCALE
        ox    = (s.SCREEN_W - map_w) // 2
        oy    = (s.SCREEN_H - map_h) // 2

        overlay = pygame.Surface((map_w, map_h), pygame.SRCALPHA)
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
        overlay = pygame.Surface((s.SCREEN_W, s.SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        self.screen.blit(overlay, (0, 0))

        cx, cy = s.SCREEN_W // 2, s.SCREEN_H // 2
        t   = self.font_large.render(title, True, color)
        sub = self.font_small.render(subtitle, True, s.C_TEXT)
        self.screen.blit(t,   t.get_rect(center=(cx, cy - 30)))
        self.screen.blit(sub, sub.get_rect(center=(cx, cy + 30)))

    # ── Restart ───────────────────────────────────────────────────────────────

    def _restart(self):
        self._init_session()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    Game().run()
