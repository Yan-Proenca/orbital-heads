"""Suporte avançado a controles (Xbox, PlayStation, Nintendo Switch e genéricos) via pygame.

Porte do gamepad.py fornecido, adaptado para o loop único do Pygame deste
projeto (em vez de um loop do Tkinter lendo eventos à parte): aqui
`GamepadManager.feed_events(events)` RECEBE a lista de eventos que main.py já
coletou com `pygame.event.get()` uma única vez por quadro, em vez de chamar
`pygame.event.get()') por conta própria — importante porque só pode haver UM
consumidor da fila de eventos do pygame por quadro; se o GamepadManager e o
InputManager chamassem `pygame.event.get()` cada um por si, um dos dois
sempre perderia eventos.

Cada controle tem uma VAGA (0, 1, 2...) na ordem em que foi conectado; quem
decide qual jogador ele controla é o jogo (ver input_handler.InputManager,
que casa vagas de controle com jogadores). Direcional (D-pad) e analógico
esquerdo viram direções; botões viram ações nomeadas ("a", "b", "x", "y",
"lb", "rb", "back", "start"), sempre no padrão do controle de Xbox: `a` é o
botão de baixo (confirma), `b` o da direita (volta), `lb`/`rb` os gatilhos
de ombro.

Cada família de controle numera os botões de um jeito, então o jogo
reconhece a família pelo nome do dispositivo e usa a tabela certa.
`button_label()` devolve o nome que aparece na tela (✕ ○ □ ▲ no
PlayStation, A B X Y no Xbox...). Para investigar um controle estranho,
rode o jogo com a variável de ambiente ORBITAL_GAMEPAD_DEBUG=1: cada botão
apertado (e o que o jogo entendeu) é impresso no terminal.
"""

import os

# O pygame só lê o controle quando a janela dele está em foco; liberamos a
# leitura em segundo plano (precisa ser definido antes de iniciar o joystick).
os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
# No Bluetooth o PS4/PS5 só aceita trocar a cor da luz no modo "completo" do SDL.
os.environ.setdefault("SDL_JOYSTICK_HIDAPI_PS4_RUMBLE", "1")
os.environ.setdefault("SDL_JOYSTICK_HIDAPI_PS5_RUMBLE", "1")

try:
    import pygame
except ImportError:  # sem pygame o jogo continua só no teclado
    pygame = None


def _load_sdl():
    """SDL2 que o pygame já carregou: dá acesso à luz do controle (barra de luz do PS4/PS5).
    Suporta Windows (SDL2.dll), Linux (libSDL2-2.0.so.0) e macOS (SDL2.framework/SDL2);
    em qualquer outro caso, o jogo segue normalmente sem controle de luz (ela é só enfeite)."""
    try:
        import ctypes
        import ctypes.util

        base = os.path.dirname(pygame.__file__)
        candidates = [
            os.path.join(base, "SDL2.dll"),                                   # Windows (pygame vendoriza)
            os.path.join(base, ".dylibs", "libSDL2-2.0.0.dylib"),             # macOS (pygame vendoriza)
            ctypes.util.find_library("SDL2-2.0"),                              # Linux (lib do sistema)
            ctypes.util.find_library("SDL2"),
            "libSDL2-2.0.so.0",
        ]
        lib = None
        for path in candidates:
            if not path:
                continue
            try:
                lib = ctypes.CDLL(path)
                break
            except OSError:
                continue
        if lib is None:
            return None
        lib.SDL_JoystickFromInstanceID.restype = ctypes.c_void_p
        lib.SDL_JoystickFromInstanceID.argtypes = [ctypes.c_int32]
        lib.SDL_JoystickHasLED.argtypes = [ctypes.c_void_p]
        lib.SDL_JoystickSetLED.argtypes = [ctypes.c_void_p] + [ctypes.c_uint8] * 3
        return lib
    except Exception:
        return None


STICK_DEADZONE = 0.5    # quanto o analógico precisa ser empurrado para contar como direção (eventos discretos de menu)
DEBUG = os.environ.get("ORBITAL_GAMEPAD_DEBUG", "") not in ("", "0")

XBOX, PLAYSTATION, SWITCH, GENERIC = "xbox", "playstation", "switch", "generic"

# Botões do controle de Xbox no pygame/SDL (Windows): também é o padrão para controles genéricos.
_XBOX_MAP = {0: "a", 1: "b", 2: "x", 3: "y", 4: "lb", 5: "rb", 6: "back", 7: "start"}
# PlayStation/Switch no SDL moderno (HIDAPI): os botões seguem a ordem dos "botões de controle" do SDL.
_SDL_ORDER_MAP = {0: "a", 1: "b", 2: "x", 3: "y", 4: "back", 6: "start", 9: "lb", 10: "rb"}
# DualShock 4 no modo antigo (DirectInput, aparece como "Wireless Controller").
_PS_LEGACY_MAP = {1: "a", 2: "b", 0: "x", 3: "y", 4: "lb", 5: "rb", 8: "back", 9: "start"}
# Alguns drivers entregam o direcional como 4 botões em vez de "hat" (cima, baixo, esquerda, direita).
_DPAD_BUTTONS = {11: (0, -1), 12: (0, 1), 13: (-1, 0), 14: (1, 0)}

# Nome do botão (padrão Xbox) -> texto mostrado na tela
LABELS = {
    XBOX: {"a": "A", "b": "B", "x": "X", "y": "Y", "lb": "LB", "rb": "RB", "start": "START", "back": "BACK"},
    PLAYSTATION: {"a": "×", "b": "○", "x": "□", "y": "▲", "lb": "L1", "rb": "R1", "start": "OPTIONS", "back": "SHARE"},
    SWITCH: {"a": "B", "b": "A", "x": "Y", "y": "X", "lb": "L", "rb": "R", "start": "+", "back": "−"},
    GENERIC: {"a": "A", "b": "B", "x": "X", "y": "Y", "lb": "LB", "rb": "RB", "start": "START", "back": "BACK"},
}
# Cor de cada botão na dica (os controles de PlayStation usam outras cores para os 4 botões de ação)
COLORS = {
    XBOX: {"a": "#31C96A", "b": "#FF4B5E", "x": "#55A9FF", "y": "#FFD84A"},
    PLAYSTATION: {"a": "#6EA8FF", "b": "#FF5B6E", "x": "#FF8FD8", "y": "#35D6A0"},
}
COLORS[SWITCH] = COLORS[GENERIC] = COLORS[XBOX]
SHOULDER_COLOR, NEUTRAL_COLOR = "#55A9FF", "#AFC3D8"

SHORT_NAMES = {XBOX: "XBOX", PLAYSTATION: "PS", SWITCH: "SWITCH", GENERIC: "GAMEPAD"}
FAMILY_NAMES = {XBOX: "Xbox", PLAYSTATION: "PlayStation", SWITCH: "Nintendo Switch", GENERIC: "genérico"}

# Nome que o SDL dá -> nome que o jogador reconhece (o resto é mostrado como vem do sistema)
FRIENDLY_NAMES = {
    "ps4 controller": "DualShock 4",
    "wireless controller": "DualShock 4",
    "ps5 controller": "DualSense",
    "ps3 controller": "DualShock 3",
    "xbox 360 controller": "Controle Xbox 360",
    "xbox one controller": "Controle Xbox One",
    "nintendo switch pro controller": "Switch Pro Controller",
}


def family_of(name):
    """Família do controle, a partir do nome que o sistema dá ao dispositivo."""
    n = (name or "").lower()
    if any(k in n for k in ("xbox", "x-box", "xinput", "x360", "microsoft")):
        return XBOX
    if any(k in n for k in ("ps3", "ps4", "ps5", "dualshock", "dualsense", "playstation", "sony",
                             "wireless controller")):
        return PLAYSTATION
    if any(k in n for k in ("nintendo", "switch", "joy-con", "pro controller")):
        return SWITCH
    return GENERIC


def button_label(name, family=XBOX):
    """Texto de um botão na tela (name em minúsculas: a, b, x, y, lb, rb, start, back)."""
    labels = LABELS.get(family, LABELS[XBOX])
    return labels.get(name.lower(), name.upper())


def button_color(name, family=XBOX):
    name = name.lower()
    if name in ("lb", "rb"):
        return SHOULDER_COLOR
    return COLORS.get(family, COLORS[XBOX]).get(name, NEUTRAL_COLOR)


def _button_map(name, family):
    if family == PLAYSTATION:
        n = (name or "").lower()
        # "Wireless Controller" (sem mais nenhuma marca) é como o DS4 se
        # anuncia via Bluetooth/DirectInput legado. Já o DualSense (PS5)
        # normalmente inclui "DualSense" ou "PS5" no nome mesmo quando
        # "Wireless Controller" também aparece (ex. "DualSense Wireless
        # Controller") — nesse caso ele já fala HIDAPI moderno, então não
        # deve cair no mapa legado só por causa da substring em comum.
        is_legacy_ds4 = "wireless controller" in n and not any(k in n for k in ("dualsense", "ps5"))
        return _PS_LEGACY_MAP if is_legacy_ds4 else _SDL_ORDER_MAP
    if family == SWITCH:
        return _SDL_ORDER_MAP
    return _XBOX_MAP


class GamepadManager:
    """Regras das vagas: cada controle ganha a vaga (= jogador) seguinte ao conectar.
    Ao desconectar, a vaga fica reservada e vazia (None): ninguém muda de jogador.
    Um controle do mesmo modelo (mesmo GUID) que volta ocupa de novo a vaga vazia dele;
    um controle diferente ganha uma vaga nova no fim, a não ser que alguma vaga tenha sido liberada (release)."""

    def __init__(self):
        self.ok = False
        self.pads = []      # vaga -> joystick, ou None se aquele controle desconectou
        self.slots = []     # vaga -> info do último controle que esteve nela (fica após desconectar)
        self.stick_dir = {}  # instance_id -> última direção do analógico (evita repetir)
        self.info = {}      # instance_id -> {"name", "family", "map", "dpad_buttons", "guid", "led"}
        self.sdl = None
        if pygame is None:
            return
        try:
            pygame.display.init()      # necessário para a fila de eventos (não abre janela de novo se já existe)
            pygame.joystick.init()
            self.ok = True
            self.sdl = _load_sdl()
            # pygame.joystick.init() não gera JOYDEVICEADDED para controles já
            # conectados ANTES do init; registramos manualmente os que já
            # estavam presentes para não perdê-los.
            for i in range(pygame.joystick.get_count()):
                try:
                    js = pygame.joystick.Joystick(i)
                    js.init()
                    self._attach(js)
                except Exception:
                    pass
        except Exception as e:
            print("Controle indisponível:", e)

    # ---- o que está conectado
    @property
    def count(self):
        """Vagas de controle, contando as desconectadas (elas continuam reservadas)."""
        return len(self.pads)

    @property
    def connected(self):
        """True se há pelo menos um controle conectado."""
        return any(self.pads)

    def is_connected(self, index):
        return 0 <= index < len(self.pads) and self.pads[index] is not None

    def is_released(self, index):
        return bool(self._slot(index).get("released"))

    def _slot(self, index):
        return self.slots[index] if 0 <= index < len(self.slots) else {}

    def family(self, index=0):
        """Família do controle nº `index` (GENERIC se não houver)."""
        return self._slot(index).get("family", GENERIC)

    def name(self, index=0):
        return self._slot(index).get("name", "")

    def led(self, index=0):
        """Cor (#RRGGBB) acesa na luz do controle, ou None se ele não tem luz controlável."""
        return self._slot(index).get("led")

    def describe(self):
        """Resumo para mostrar ao jogador, ex.: 'Xbox Wireless Controller (Xbox)'."""
        return [f"{self.name(i)} ({FAMILY_NAMES[self.family(i)]})" for i in range(self.count)]

    def set_led(self, index, color):
        """Acende a luz do controle com `color` (#RRGGBB). Só funciona em controles com luz (PS4/PS5)."""
        js = self.pads[index] if self.is_connected(index) else None
        if js is None or self.sdl is None:
            return
        slot = self.slots[index]
        if slot.get("led") == color or slot.get("no_led"):
            return  # já está com essa cor, ou o controle não tem luz: chamado a cada quadro, sai rápido
        try:
            ptr = self.sdl.SDL_JoystickFromInstanceID(js.get_instance_id())
            if not ptr or not self.sdl.SDL_JoystickHasLED(ptr):
                slot["no_led"] = True
                return
            r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
            if self.sdl.SDL_JoystickSetLED(ptr, r, g, b) == 0:
                slot["led"] = color
            else:
                slot["no_led"] = True
        except Exception:
            slot["no_led"] = True  # luz é enfeite: falhar não pode derrubar o jogo

    def release(self, index):
        """Libera a vaga de um controle desconectado: o próximo controle de qualquer modelo pode ocupá-la."""
        if 0 <= index < len(self.pads) and self.pads[index] is None:
            self.slots[index] = {"released": True}

    def _index_of(self, instance_id):
        for i, js in enumerate(self.pads):
            if js is not None and js.get_instance_id() == instance_id:
                return i
        return None

    def _register(self, js):
        name = js.get_name()  # nome cru: decide a família e o mapa de botões
        family = family_of(name)
        try:
            hats = js.get_numhats()
        except Exception:
            hats = 1
        try:
            buttons = js.get_numbuttons()
        except Exception:
            buttons = 0
        try:
            guid = js.get_guid()
        except Exception:
            guid = name
        info = self.info[js.get_instance_id()] = {
            "name": FRIENDLY_NAMES.get(name.lower(), name),
            "family": family,
            "guid": guid,
            "led": None,
            "map": _button_map(name, family),
            # sem "hat" e com botões de sobra: o direcional vem como botões 11-14
            "dpad_buttons": hats == 0 and buttons >= 15 and family in (PLAYSTATION, SWITCH),
        }
        return info

    def _attach(self, js):
        """Controle conectado: volta para a vaga vazia do mesmo modelo, ou ganha uma vaga nova. Devolve a vaga."""
        if self._index_of(js.get_instance_id()) is not None:
            return None
        info = self._register(js)
        index = next((i for i, p in enumerate(self.pads)
                      if p is None and self.slots[i].get("guid") == info["guid"]), None)
        if index is None:  # sem vaga do mesmo modelo: usa a primeira vaga liberada
            index = next((i for i, p in enumerate(self.pads) if p is None and self.slots[i].get("released")), None)
        if index is None:
            self.pads.append(js)
            self.slots.append(info)
            index = len(self.pads) - 1
        else:
            self.pads[index], self.slots[index] = js, info
        print(f"Controle {index + 1} conectado: {info['name']} ({FAMILY_NAMES[info['family']]})")
        return index

    def _detach(self, instance_id):
        """Controle desconectado: a vaga fica vazia, mas reservada. Devolve a vaga."""
        index = self._index_of(instance_id)
        self.stick_dir.pop(instance_id, None)
        self.info.pop(instance_id, None)
        if index is None:
            return None
        self.pads[index] = None
        print(f"Controle {index + 1} desconectado: {self.name(index)}")
        return index

    def feed_events(self, events):
        """Processa os eventos de joystick dentro de `events` (a lista que
        main.py já coletou com pygame.event.get() neste quadro — NÃO chamamos
        pygame.event.get() aqui, para não competir com o InputManager pela
        fila). Retorna uma lista de (vaga, tipo, valor):
        ("dir", (dx, dy)) para direções discretas (usado pelos menus),
        ("button", nome) para botões, e (vaga, "changed", True/False) quando
        um controle é conectado/desconectado."""
        if not self.ok:
            return []
        out = []
        for ev in events:
            if ev.type == pygame.JOYDEVICEADDED:
                try:
                    index = self._attach(pygame.joystick.Joystick(ev.device_index))
                except Exception:
                    index = None
                if index is not None:
                    out.append((index, "changed", True))
            elif ev.type == pygame.JOYDEVICEREMOVED:
                index = self._detach(ev.instance_id)
                if index is not None:
                    out.append((index, "changed", False))
            elif ev.type == pygame.JOYHATMOTION:
                idx = self._index_of(ev.instance_id)
                hx, hy = ev.value
                if idx is not None and (hx or hy):
                    # Hat: y=+1 é para cima; na tela y cresce para baixo. Diagonal prioriza horizontal.
                    out.append((idx, "dir", (hx, 0) if hx else (0, -hy)))
            elif ev.type == pygame.JOYAXISMOTION and ev.axis in (0, 1):
                idx = self._index_of(ev.instance_id)
                if idx is not None:
                    d = self._stick(ev.instance_id)
                    if d and d != self.stick_dir.get(ev.instance_id):
                        out.append((idx, "dir", d))
                    self.stick_dir[ev.instance_id] = d
            elif ev.type == pygame.JOYBUTTONDOWN:
                idx = self._index_of(ev.instance_id)
                if idx is None:
                    continue
                info = self.info.get(ev.instance_id, {})
                if info.get("dpad_buttons") and ev.button in _DPAD_BUTTONS:
                    out.append((idx, "dir", _DPAD_BUTTONS[ev.button]))
                    continue
                name = info.get("map", _XBOX_MAP).get(ev.button)
                if DEBUG:
                    print(f"[gamepad] botão {ev.button} de {info.get('name')!r} -> {name or 'sem função'}")
                if name:
                    out.append((idx, "button", name))
        return out

    def _stick(self, instance_id):
        idx = self._index_of(instance_id)
        if idx is None:
            return None
        js = self.pads[idx]
        x, y = js.get_axis(0), js.get_axis(1)
        if max(abs(x), abs(y)) < STICK_DEADZONE:
            return None
        if abs(x) >= abs(y):
            return (1, 0) if x > 0 else (-1, 0)
        return (0, 1) if y > 0 else (0, -1)

    def button_down(self, index, name):
        """Estado contínuo (não por evento) de um botão nomeado ("a", "lb", ...)
        do controle na vaga `index`. Útil para ações "seguradas" (mirar, acelerar)
        em vez de apertos únicos."""
        if not self.is_connected(index):
            return False
        js = self.pads[index]
        info = self.info.get(js.get_instance_id(), {})
        mapping = info.get("map", _XBOX_MAP)
        for button, mapped in mapping.items():
            if mapped == name and button < js.get_numbuttons():
                return bool(js.get_button(button))
        return False

    def axis_dir(self, index, deadzone=None):
        """Direção contínua do analógico esquerdo + D-pad (hat) do controle na
        vaga `index`, como (dx, dy) com cada eixo em -1/0/1. Usado para
        movimento no jogo (diferente de _stick(), que gera eventos discretos
        para navegação de menu)."""
        if not self.is_connected(index):
            return (0, 0)
        js = self.pads[index]
        dz = STICK_DEADZONE if deadzone is None else deadzone
        dx = dy = 0
        if js.get_numaxes() > 1:
            ax, ay = js.get_axis(0), js.get_axis(1)
            if abs(ax) > dz:
                dx = 1 if ax > 0 else -1
            if abs(ay) > dz:
                dy = 1 if ay > 0 else -1
        if dx == 0 and dy == 0 and js.get_numhats() > 0:
            hx, hy = js.get_hat(0)
            dx, dy = hx, -hy
        return (dx, dy)

    def driving_state(self, index=0):
        """Estado contínuo da perseguição. Não altera os eventos dos menus/arena."""
        state = dict(steer=0.0, throttle=0.0, brake=0.0, boost=False, wall=False)
        if not self.ok or not self.is_connected(index):
            return state
        try:
            js = self.pads[index]
            info = self.info.get(js.get_instance_id(), {})
            x = js.get_axis(0) if js.get_numaxes() else 0
            state["steer"] = 0.0 if abs(x) < .16 else max(-1.0, min(1.0, x))
            if js.get_numhats():
                hx, hy = js.get_hat(0)
                if hx:
                    state["steer"] = float(hx)
                state["throttle"] = float(hy > 0)
                state["brake"] = float(hy < 0)
            mapping = info.get("map", _XBOX_MAP)
            for button, name in mapping.items():
                if button < js.get_numbuttons() and js.get_button(button):
                    if name == "a":
                        state["throttle"] = 1.0
                    elif name == "b":
                        state["brake"] = 1.0
                    elif name == "rb":
                        state["boost"] = True
                    elif name == "x":
                        state["wall"] = True
            if info.get("dpad_buttons"):
                for button, direction in _DPAD_BUTTONS.items():
                    if button < js.get_numbuttons() and js.get_button(button):
                        if direction[0]:
                            state["steer"] = float(direction[0])
                        elif direction[1] < 0:
                            state["throttle"] = 1.0
                        else:
                            state["brake"] = 1.0
        except Exception:
            pass  # remoção física durante um quadro: a próxima sondagem atualiza a lista
        return state

    def shutdown(self):
        if self.ok:
            try:
                pygame.joystick.quit()
            except Exception:
                pass
