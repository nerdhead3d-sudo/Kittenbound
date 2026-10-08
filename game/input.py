"""Input unificato: tastiera/mouse + controller (layout Xbox, anche PlayStation via SDL).

Controller nel dungeon:
    Stick sinistro / croce   muovi          Stick destro   mira
    X  o  RT                 attacco        A  o  LT       schivata
    Y                        magia          B              pozione
    RB                       parata
    View (Back)              mappa          LB             recall all'hub
    Start                    pausa
Nell'hub e nei menu: A conferma/interagisci, B indietro, croce su/giù per scegliere.

Il gioco passa da solo alla modalità controller quando lo usi e torna a mouse/tastiera
appena muovi il mouse o premi un tasto: cambiano mira e suggerimenti a schermo.
"""
import pygame

try:                                    # API "GameController" di SDL: tasti standard per ogni pad
    from pygame._sdl2 import controller as _sdl_controller
except ImportError:                     # pygame senza _sdl2: niente controller, solo tastiera
    _sdl_controller = None

DEADZONE      = 0.25
AIM_DEADZONE  = 0.35
TRIGGER_PRESS = 0.5
_AXIS_MAX     = 32767.0

# Pulsanti → "azione" logica (main.py la traduce nel tasto equivalente in base allo stato)
BUTTON_ACTIONS = {
    "a": "confirm", "b": "back", "x": "attack", "y": "spell",
    "leftshoulder": "recall", "rightshoulder": "parry",
    "back": "map", "start": "pause",
    "dpad_up": "up", "dpad_down": "down", "dpad_left": "left", "dpad_right": "right",
}


class InputManager:
    _instance = None

    @classmethod
    def get(cls) -> "InputManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.using_controller = False
        self._pads: dict = {}                # instance_id -> Controller
        self._joys: dict = {}                # instance_id -> Joystick (vedi _open)
        self._button_names: dict = {}
        self._lt_down = self._rt_down = False
        if _sdl_controller is None:
            return
        _sdl_controller.init()
        for name in BUTTON_ACTIONS:
            const = getattr(pygame, f"CONTROLLER_BUTTON_{name.upper()}", None)
            if const is not None:
                self._button_names[const] = name
        for i in range(_sdl_controller.get_count()):
            self._open(i)

    # ── Collegamento ──────────────────────────────────────────────────────────

    def _open(self, device_index: int):
        if _sdl_controller is None or not _sdl_controller.is_controller(device_index):
            return
        try:
            pad = _sdl_controller.Controller(device_index)
            # Aperto anche come joystick: pygame 2.6 tiene una tabella interna dei joystick
            # e va in errore (KeyError dentro event.get) se arrivano eventi da un dispositivo
            # che non conosce, ad es. un DualSense che si ricollega via Bluetooth.
            joy = pygame.joystick.Joystick(device_index)
        except pygame.error:
            return
        iid = joy.get_instance_id()
        self._pads[iid] = pad
        self._joys[iid] = joy

    @property
    def connected(self) -> bool:
        return bool(self._pads)

    # ── Eventi ────────────────────────────────────────────────────────────────

    def handle_event(self, event) -> "str | None":
        """Aggiorna lo stato e restituisce l'azione premuta sul controller (o None)."""
        et = event.type
        if et in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
            if self.using_controller:
                self.using_controller = False
                pygame.mouse.set_visible(True)
            return None
        if _sdl_controller is None:
            return None
        if et in (pygame.CONTROLLERDEVICEADDED, pygame.JOYDEVICEADDED):
            if not any(j.get_instance_id() == pygame.joystick.Joystick(event.device_index).get_instance_id()
                       for j in self._joys.values()):
                self._open(event.device_index)
        elif et in (pygame.CONTROLLERDEVICEREMOVED, pygame.JOYDEVICEREMOVED):
            self._pads.pop(event.instance_id, None)
            self._joys.pop(event.instance_id, None)
            if not self._pads:
                self._set_controller_mode(False)
        elif et == pygame.CONTROLLERBUTTONDOWN:
            self._set_controller_mode(True)
            return BUTTON_ACTIONS.get(self._button_names.get(event.button))
        elif et == pygame.CONTROLLERAXISMOTION:
            value = event.value / _AXIS_MAX
            if abs(value) > DEADZONE:
                self._set_controller_mode(True)
            # I grilletti sono analogici: diventano "premuti" quando superano la soglia
            if event.axis == pygame.CONTROLLER_AXIS_TRIGGERLEFT:
                pressed = value > TRIGGER_PRESS
                fired, self._lt_down = pressed and not self._lt_down, pressed
                if fired:
                    return "dodge"
        return None

    @staticmethod
    def events() -> list:
        """pygame.event.get() a prova di crash: se pygame inciampa su un evento di un
        controller appena ricollegato, si perde quel frame di input invece di chiudere il gioco."""
        try:
            return pygame.event.get()
        except (SystemError, KeyError):
            return []

    def _set_controller_mode(self, on: bool):
        if on != self.using_controller:
            self.using_controller = on
            pygame.mouse.set_visible(not on)

    # ── Stato continuo ────────────────────────────────────────────────────────

    def _axis(self, axis) -> float:
        best = 0.0
        for pad in self._pads.values():
            v = pad.get_axis(axis) / _AXIS_MAX
            if abs(v) > abs(best):
                best = v
        return best

    def _button(self, name: str) -> bool:
        const = getattr(pygame, f"CONTROLLER_BUTTON_{name.upper()}", None)
        return const is not None and any(pad.get_button(const) for pad in self._pads.values())

    def move_vector(self) -> pygame.math.Vector2:
        """Direzione di movimento (lunghezza ≤ 1): WASD/frecce, stick sinistro o croce."""
        keys = pygame.key.get_pressed()
        v = pygame.math.Vector2(
            float((keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])),
            float((keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP])),
        )
        if self._pads:
            stick = pygame.math.Vector2(self._axis(pygame.CONTROLLER_AXIS_LEFTX),
                                        self._axis(pygame.CONTROLLER_AXIS_LEFTY))
            if stick.length() > DEADZONE:
                # deadzone radiale riscalata: movimento analogico fluido da 0 a 1
                mag = min(1.0, (stick.length() - DEADZONE) / (1 - DEADZONE))
                v += stick.normalize() * mag
            v.x += self._button("dpad_right") - self._button("dpad_left")
            v.y += self._button("dpad_down") - self._button("dpad_up")
        if v.length() > 1:
            v.scale_to_length(1)
        return v

    def aim_vector(self) -> "pygame.math.Vector2 | None":
        """Direzione dello stick destro, se inclinato abbastanza."""
        if not self._pads:
            return None
        v = pygame.math.Vector2(self._axis(pygame.CONTROLLER_AXIS_RIGHTX),
                                self._axis(pygame.CONTROLLER_AXIS_RIGHTY))
        return v.normalize() if v.length() > AIM_DEADZONE else None

    def attack_held(self) -> bool:
        """Attacco tenuto premuto: click sinistro, X o grilletto destro."""
        if pygame.mouse.get_pressed()[0]:
            return True
        return bool(self._pads) and (self._button("x")
                                     or self._axis(pygame.CONTROLLER_AXIS_TRIGGERRIGHT) > TRIGGER_PRESS)

    # ── Etichette dei comandi ─────────────────────────────────────────────────

    _GLYPHS = {
        "xbox": dict(A="A", B="B", X="X", Y="Y", LB="LB", RB="RB", LT="LT", RT="RT",
                     VIEW="View", START="Start", LS="Stick sx", RS="Stick dx"),
        "ps":   dict(A="✕", B="○", X="□", Y="△", LB="L1", RB="R1", LT="L2", RT="R2",
                     VIEW="Create", START="Options", LS="Stick sx", RS="Stick dx"),
    }

    @property
    def pad_style(self) -> str:
        """"ps" per DualSense/DualShock, altrimenti "xbox" (stesso schema di tasti)."""
        for pad in self._pads.values():
            name = (pad.name or "").lower()
            if any(k in name for k in ("dualsense", "dualshock", "ps4", "ps5", "playstation")):
                return "ps"
        return "xbox"

    def label(self, keyboard: str, pad: str) -> str:
        """Testo del comando per il dispositivo in uso. pad può contenere {A}, {B}, {RT}...
        es. label("[E] Magie", "[{A}] Magie") → "[✕] Magie" con un DualSense."""
        if not self.using_controller:
            return keyboard
        return pad.format(**self._GLYPHS[self.pad_style])
