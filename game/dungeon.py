import collections
import pygame
import random
from game import settings as s
from game.room import Room
from game.merchant import Merchant
from game.enemy import (RattoGuardia, RattoEsploratore, RattoLancia,
                        RattoStregone, RattoSoldato, RattoFromboliere, TopoArmaturato)

OPPOSITE  = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
DIR_DELTA = {'N': (0, -1), 'S': (0, 1), 'E': (1, 0), 'W': (-1, 0)}


class Dungeon:
    """
    Genera un dungeon come insieme connesso di Room collegate da porte.

    Algoritmo:
    1. Seleziona N posizioni nella griglia con "growing region" (garantisce
       che le posizioni scelte formino un grafo connesso di adiacenze).
    2. Spanning tree (Prim) sulle posizioni → connettività garantita.
    3. Extra edge casuali → crea qualche loop per rendere il dungeon meno
       lineare.
    4. BFS per trovare la stanza più lontana dallo start (end room).
    5. Difficoltà dei nemici scalata con la distanza BFS dallo start.
    """

    def __init__(self, floor: int = 1, seed: int | None = None, water: bool = False):
        self.floor              = floor
        self.seed               = seed    # stesso seme = stesso dungeon (stanze, muri, nemici)
        self.water              = water   # Fogne: canali d'acqua nelle stanze
        self.grid: dict         = {}      # (col, row) -> Room
        self.start_pos: tuple   = (0, 0)
        self.end_pos: tuple     = (0, 0)
        self.current_pos: tuple = (0, 0)
        self.bag_pos            = None
        self.entry_dir          = None    # porta d'ingresso nella stanza attuale (None = centro)
        if seed is None:
            self._generate()
        else:
            # genera col seme, poi rimette il caso com'era: il combattimento resta imprevedibile
            state = random.getstate()
            random.seed(seed)
            try:
                self._generate()
            finally:
                random.setstate(state)

    # ── Proprietà ─────────────────────────────────────────────────────────────

    @property
    def current_room(self) -> Room:
        return self.grid[self.current_pos]

    @property
    def all_rooms_cleared(self) -> bool:
        return all(r.cleared for r in self.grid.values())

    # ── Generazione ───────────────────────────────────────────────────────────

    def _generate(self):
        positions = self._select_positions()
        pos_set   = set(positions)

        edges    = self._spanning_tree(positions, pos_set)
        edge_set = {frozenset([v, n]) for v, n, _ in edges}

        # Extra connessioni (30 % per ogni coppia adiacente non ancora connessa)
        for v in positions:
            for d, (dc, dr) in DIR_DELTA.items():
                n = (v[0] + dc, v[1] + dr)
                if n in pos_set:
                    key = frozenset([v, n])
                    if key not in edge_set and random.random() < 0.30:
                        edge_set.add(key)
                        edges.append((v, n, d))

        # Mappa porte
        doors_map = {pos: {} for pos in positions}
        for v, n, d in edges:
            doors_map[v][d] = True
            doors_map[n][OPPOSITE[d]] = True

        # Start e End
        self.start_pos = positions[0]
        distances      = self._bfs_dist(self.start_pos, doors_map, pos_set)
        self.end_pos   = max(distances, key=distances.get)

        # Stanze speciali: le 2 con maggiore distanza BFS (escluse start ed end)
        non_terminal = [p for p in positions
                        if p != self.start_pos and p != self.end_pos]
        non_terminal.sort(key=lambda p: distances.get(p, 0), reverse=True)
        special_count = min(s.SPECIAL_ROOMS_COUNT, len(non_terminal))
        special_set   = set(non_terminal[:special_count])

        # Crea Room con tipo assegnato
        for pos in positions:
            is_end = (pos == self.end_pos)
            dist   = distances.get(pos, 0)

            if pos == self.start_pos:
                rtype = s.ROOM_TYPE_START
            elif pos == self.end_pos:
                rtype = s.ROOM_TYPE_BOSS
            elif pos in special_set:
                rtype = s.ROOM_TYPE_SPECIAL
            else:
                rtype = s.ROOM_TYPE_NORMAL

            specs = self._enemy_specs(dist, rtype)
            wet = (self.water and rtype in (s.ROOM_TYPE_NORMAL, s.ROOM_TYPE_SPECIAL)
                   and random.random() < s.WATER_ROOM_CHANCE)
            self.grid[pos] = Room(doors=doors_map[pos], enemy_specs=specs,
                                  is_end=is_end, room_type=rtype, floor=self.floor, water=wet)

        self._place_merchant(doors_map)

        self.current_pos = self.start_pos
        self.current_room.visited = True

    def _place_merchant(self, doors_map: dict):
        """Mercante nascosto: in metà dei piani, in una stanza normale, se possibile un vicolo cieco."""
        self.merchant_pos = None
        if random.random() >= s.MERCHANT_CHANCE:
            return
        normal = [p for p, r in self.grid.items() if r.room_type == s.ROOM_TYPE_NORMAL]
        if not normal:
            return
        dead_ends = [p for p in normal if sum(1 for v in doors_map[p].values() if v) == 1]
        pos  = random.choice(dead_ends or normal)
        room = self.grid[pos]
        x, y = room._find_spawn_near(room.pixel_w * random.choice((0.3, 0.7)), room.pixel_h * 0.45)
        room.merchant     = Merchant(x, y, random.Random(random.random()))
        self.merchant_pos = pos

    def _select_positions(self) -> list:
        """
        Espande una regione connessa nella griglia fino a raggiungere
        DUNGEON_ROOMS posizioni. Garantisce connettività fisica.
        """
        start   = (random.randint(0, s.DUNGEON_COLS - 1),
                   random.randint(0, s.DUNGEON_ROWS - 1))
        placed  = [start]
        border  = set()

        def add_neighbors(pos):
            for dc, dr in DIR_DELTA.values():
                n = (pos[0] + dc, pos[1] + dr)
                if (0 <= n[0] < s.DUNGEON_COLS and
                        0 <= n[1] < s.DUNGEON_ROWS and
                        n not in placed and n not in border):
                    border.add(n)

        add_neighbors(start)

        while len(placed) < s.DUNGEON_ROOMS and border:
            pos = random.choice(list(border))
            border.discard(pos)
            placed.append(pos)
            add_neighbors(pos)

        return placed

    def _spanning_tree(self, positions: list, pos_set: set) -> list:
        """Prim su posizioni fisicamente adiacenti → archi dello spanning tree."""
        visited  = {positions[0]}
        edges    = []
        edge_set = set()

        while len(visited) < len(positions):
            candidates = [
                (v, (v[0] + dc, v[1] + dr), d)
                for v in visited
                for d, (dc, dr) in DIR_DELTA.items()
                if (v[0] + dc, v[1] + dr) in pos_set
                and (v[0] + dc, v[1] + dr) not in visited
            ]
            if not candidates:
                break
            v, n, d = random.choice(candidates)
            key = frozenset([v, n])
            if key not in edge_set:
                edge_set.add(key)
                edges.append((v, n, d))
            visited.add(n)

        return edges

    def _bfs_dist(self, start: tuple, doors_map: dict, pos_set: set) -> dict:
        dist  = {start: 0}
        queue = collections.deque([start])
        while queue:
            pos = queue.popleft()
            for d in doors_map.get(pos, {}):
                dc, dr = DIR_DELTA[d]
                n = (pos[0] + dc, pos[1] + dr)
                if n in pos_set and n not in dist:
                    dist[n] = dist[pos] + 1
                    queue.append(n)
        return dist

    def _enemy_specs(self, dist: int, room_type: str) -> list:
        if room_type == s.ROOM_TYPE_START:
            return []

        if room_type == s.ROOM_TYPE_BOSS:
            return [(TopoArmaturato, 1)]

        if room_type == s.ROOM_TYPE_SPECIAL:
            return random.choice([
                # Imboscata: uccidi l'esploratore in fretta o arrivano rinforzi
                [(RattoEsploratore, 1), (RattoGuardia, 3)],
                # Fortino: spade lunghe + soldato corazzato + stregone + tiratore
                [(RattoLancia, 2), (RattoSoldato, 1), (RattoStregone, 1), (RattoFromboliere, 1)],
                # Batteria: tiratori protetti da guardie
                [(RattoFromboliere, 2), (RattoGuardia, 2)],
                # Colonia difesa: numeri elevati con supporto magico
                [(RattoGuardia, 4), (RattoStregone, 1)],
            ])

        # ROOM_TYPE_NORMAL — difficoltà scalata sulla distanza BFS
        if dist == 1:
            return random.choice([
                [(RattoGuardia, 2)],
                [(RattoGuardia, 1), (RattoFromboliere, 1)],
            ])
        elif dist == 2:
            return random.choice([
                [(RattoGuardia, 2), (RattoLancia, 1)],
                [(RattoGuardia, 1), (RattoEsploratore, 1)],
                [(RattoGuardia, 1), (RattoLancia, 1), (RattoFromboliere, 1)],
            ])
        elif dist == 3:
            return random.choice([
                [(RattoLancia, 1), (RattoStregone, 1), (RattoGuardia, 1)],
                [(RattoGuardia, 2), (RattoSoldato, 1)],
                [(RattoEsploratore, 1), (RattoLancia, 1), (RattoFromboliere, 1)],
                [(RattoFromboliere, 2), (RattoSoldato, 1)],
            ])
        else:  # dist >= 4
            return random.choice([
                [(RattoStregone, 1), (RattoSoldato, 1), (RattoFromboliere, 1)],
                [(RattoGuardia, 2), (RattoLancia, 1), (RattoSoldato, 1)],
                [(RattoSoldato, 2), (RattoEsploratore, 1)],
                [(RattoFromboliere, 2), (RattoLancia, 1), (RattoStregone, 1)],
            ])

    # ── Transizione stanza ────────────────────────────────────────────────────

    def try_transition(self, player) -> str | None:
        """
        Controlla se il player ha attraversato una porta.
        Aggiorna current_pos e riposiziona il player nella nuova stanza.
        Restituisce la direzione della transizione o None.
        """
        room = self.current_room
        if room._locked:          # stanza in lockdown: uscite bloccate
            return None
        t    = s.TILE_SIZE   # soglia: player nell'area del tile di bordo

        direction = None
        if   player.pos.y < t              and room.doors.get('N'): direction = 'N'
        elif player.pos.y > room.pixel_h-t and room.doors.get('S'): direction = 'S'
        elif player.pos.x > room.pixel_w-t and room.doors.get('E'): direction = 'E'
        elif player.pos.x < t              and room.doors.get('W'): direction = 'W'

        if direction is None:
            return None

        dc, dr   = DIR_DELTA[direction]
        next_pos = (self.current_pos[0] + dc, self.current_pos[1] + dr)
        if next_pos not in self.grid:
            return None

        self.current_pos = next_pos
        self.entry_dir   = OPPOSITE[direction]      # da che porta sei entrato (per il salvataggio)
        self.grid[next_pos].enter(player, OPPOSITE[direction])
        return direction
