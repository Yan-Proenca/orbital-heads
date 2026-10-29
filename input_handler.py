"""
input_handler.py — entrada de teclado e controle (USB/Bluetooth) unificada.

Mantém a mesma ideia da classe Input original (Tkinter): um conjunto `held`
com as ações atualmente pressionadas e um conjunto `pressed` com as que
acabaram de ser pressionadas neste quadro (consumido uma vez, para pulo/dash
não repetirem via auto-repeat).

A diferença para a versão Tkinter é que aqui as AÇÕES lógicas ("p1_left",
"p2_fire", ...) já vêm resolvidas a partir de teclado OU joystick, então o
resto do jogo (player.py) não precisa saber se o P1 está jogando com teclado
ou com um controle Xbox/PlayStation conectado por Bluetooth.
"""
import pygame

import settings as S
from gamepad import GamepadManager

# nome da tecla (string, como em settings.PLAYER_DEFS) -> constante pygame
_KEYMAP = {
    "a": pygame.K_a, "d": pygame.K_d, "w": pygame.K_w, "s": pygame.K_s,
    "space": pygame.K_SPACE, "return": pygame.K_RETURN,
    "left": pygame.K_LEFT, "right": pygame.K_RIGHT, "up": pygame.K_UP, "down": pygame.K_DOWN,
    "escape": pygame.K_ESCAPE, "r": pygame.K_r, "m": pygame.K_m, "q": pygame.K_q,
    "f11": pygame.K_F11, "f": pygame.K_f,
    # teclado numérico (usado pelo Jogador 4 por padrão): pygame.key.key_code()
    # não entende "kp4" nem o nome nativo "[4]" que pygame.key.name() devolve
    # para essas teclas, então mapeamos os dois lados nós mesmos.
    "kp0": pygame.K_KP0, "kp1": pygame.K_KP1, "kp2": pygame.K_KP2, "kp3": pygame.K_KP3,
    "kp4": pygame.K_KP4, "kp5": pygame.K_KP5, "kp6": pygame.K_KP6, "kp7": pygame.K_KP7,
    "kp8": pygame.K_KP8, "kp9": pygame.K_KP9, "kp_enter": pygame.K_KP_ENTER,
}
# constante pygame -> nome "amigável" (o inverso de boa parte do _KEYMAP acima);
# usado para exibir e para reconverter uma tecla capturada por evento de volta a
# um nome estável, já que pygame.key.name() não bate com nossos nomes para o
# teclado numérico (e para alguns símbolos a mais tarde).
_REVERSE_FRIENDLY = {code: name for name, code in _KEYMAP.items()}


def _resolve_key(name):
    """Resolve um nome de tecla para seu keycode pygame. Usa o _KEYMAP fixo
    primeiro (rápido, cobre os nomes usados nos binds padrão) e cai para
    pygame.key.key_code() para QUALQUER outra tecla do teclado (letras fora
    de a/d/w/s, números, F1-F12, teclado numérico, etc.) — isso é o que
    permite à tela de remapeamento aceitar qualquer tecla que o jogador
    pressionar, não só as pré-cadastradas em _KEYMAP."""
    if name in _KEYMAP:
        return _KEYMAP[name]
    try:
        return pygame.key.key_code(name)
    except (ValueError, pygame.error):
        raise ValueError(f"tecla desconhecida: {name}")


def key_name_for_rebind(keycode):
    """Converte um keycode (vindo de um evento KEYDOWN real) para o nome que
    rebind_key()/_resolve_key() aceitam de volta. Preferimos _REVERSE_FRIENDLY
    (cobre o teclado numérico, cujo nome nativo do pygame não bate com o que
    usamos) e caímos para pygame.key.name() para qualquer outra tecla."""
    if keycode in _REVERSE_FRIENDLY:
        return _REVERSE_FRIENDLY[keycode]
    return pygame.key.name(keycode)


def display_label(name):
    """Nome de exibição curto e legível para uma tecla, para a tela de
    configurações (ex.: 'kp4' -> 'NUM 4', 'space' -> 'ESPAÇO', 'a' -> 'A')."""
    special = {
        "space": "ESPAÇO", "return": "ENTER", "kp_enter": "ENTER NUM.", "escape": "ESC",
        "left": "◄", "right": "►", "up": "▲", "down": "▼",
        "left shift": "SHIFT ESQ.", "right shift": "SHIFT DIR.",
        "left ctrl": "CTRL ESQ.", "right ctrl": "CTRL DIR.",
        "left alt": "ALT ESQ.", "right alt": "ALT DIR.",
    }
    if name in special:
        return special[name]
    if name.startswith("kp") and name[2:].isdigit():
        return f"NUM {name[2:]}"
    if len(name) == 1:
        return name.upper()
    return name.upper()


class PlayerBinding:
    """Mapeamento de ações lógicas (left/right/jump/dash/fire) para teclado + joystick de UM jogador."""

    def __init__(self, key_names, gamepad_slot=None):
        self.key_codes = {action: _resolve_key(name) for action, name in key_names.items()}
        self.gamepad_slot = gamepad_slot   # None = sem controle atribuído a este jogador; senão, vaga do GamepadManager


class InputManager:
    """
    Centraliza teclado + controles (via gamepad.GamepadManager, que entende
    Xbox/PlayStation/Switch/genérico e trata conexão/desconexão dinâmica).
    Suporta de 1 a settings.MAX_PLAYERS jogadores simultâneos.

    API compatível com o jogo original:
        input.held    -> set de ações "p1_left", "p1_fire", "p2_jump", ... pressionadas agora
        input.pressed -> set das que ficaram pressionadas NESTE quadro (edge-trigger)
        input.take_pressed() -> retorna e limpa 'pressed' (chamar 1x por quadro)

    O polling do GamepadManager não chama pygame.event.get() por conta
    própria: main.py coleta os eventos uma vez por quadro e os repassa tanto
    para handle_event() quanto, agregados, para o GamepadManager via
    feed_events(), evitando dois consumidores da mesma fila de eventos.
    """

    def __init__(self):
        self.held = set()
        self.pressed = set()
        self.gamepad = GamepadManager()
        self.bindings = [PlayerBinding(S.PLAYER_DEFS[i]["key_names"], gamepad_slot=None)
                          for i in range(S.MAX_PLAYERS)]
        self._auto_assign_gamepads()
        self.text_input_active = False     # tela de remapeamento de teclas/controle (ver game.py)
        self.last_key_pressed = None       # usado pela tela "pressione uma tecla" do remapeamento
        self.last_gamepad_button = None    # (vaga, nome_botão) usado pela mesma tela, para remapear por controle

    # ------------------------------------------------------------ controles (USB e Bluetooth)
    @property
    def joysticks(self):
        """Compatibilidade com código que ainda espera `input.joysticks` como um
        mapeamento {vaga: objeto com get_numaxes/get_axis/...}. Internamente a
        fonte de verdade agora é self.gamepad (GamepadManager); isto apenas
        espelha as vagas ocupadas para quem (menu_input.py) só precisa saber
        "quantos controles existem" e ler eixos/hats brutos para navegação."""
        return {i: self.gamepad.pads[i] for i in range(self.gamepad.count) if self.gamepad.pads[i] is not None}

    def _auto_assign_gamepads(self):
        """1º controle -> jogador 1, 2º -> jogador 2, etc. (até MAX_PLAYERS).
        A tela de configurações permite reatribuir manualmente — ver game.py."""
        taken = {b.gamepad_slot for b in self.bindings if b.gamepad_slot is not None}
        free_slots = [i for i in range(self.gamepad.count)
                      if self.gamepad.is_connected(i) and i not in taken]
        for binding in self.bindings:
            if binding.gamepad_slot is None and free_slots:
                binding.gamepad_slot = free_slots.pop(0)

    def assign_gamepad(self, player_idx, slot):
        """Atribui manualmente uma vaga de controle (ou None para voltar ao
        teclado) a um jogador. Se outro jogador já estava usando essa vaga,
        ele a perde (volta ao teclado) — uma vaga de controle nunca fica
        atribuída a dois jogadores ao mesmo tempo."""
        if not (0 <= player_idx < len(self.bindings)):
            return
        if slot is not None:
            for i, b in enumerate(self.bindings):
                if i != player_idx and b.gamepad_slot == slot:
                    b.gamepad_slot = None
        self.bindings[player_idx].gamepad_slot = slot

    # mantido por compatibilidade com código/testes anteriores que chamavam assign_joystick
    assign_joystick = assign_gamepad

    def player_uses_gamepad(self, player_idx):
        b = self.bindings[player_idx] if 0 <= player_idx < len(self.bindings) else None
        return b is not None and b.gamepad_slot is not None and self.gamepad.is_connected(b.gamepad_slot)

    # ------------------------------------------------------------ eventos
    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and self.text_input_active:
            self.last_key_pressed = event.key

    def feed_gamepad_events(self, events):
        """Chamado por main.py uma vez por quadro com a lista de eventos já
        coletada (pygame.event.get()). Repassa ao GamepadManager (conectar/
        desconectar, botões, direções de D-pad/analógico para menus) e
        atualiza as atribuições automáticas quando a lista de controles muda."""
        out = self.gamepad.feed_events(events)
        changed = False
        for idx, kind, value in out:
            if kind == "changed":
                changed = True
                if value is False:
                    # controle sumiu: libera a vaga do jogador que o usava, ele volta pro teclado
                    for b in self.bindings:
                        if b.gamepad_slot == idx:
                            b.gamepad_slot = None
            elif kind == "button" and self.text_input_active:
                self.last_gamepad_button = (idx, value)
        if changed:
            self._auto_assign_gamepads()
        return out

    # ------------------------------------------------------------ atualização por quadro
    def update(self):
        """Lê o estado atual de teclado + controles e recalcula held/pressed.
        Chamar uma vez por quadro, depois de pygame.event.pump()/event.get()."""
        keys = pygame.key.get_pressed()
        new_held = set()

        def is_down(code):
            # keys é um pygame.key.ScancodeWrapper: ele sabe indexar corretamente
            # por QUALQUER constante K_*, inclusive as "altas" (setas, F11, etc.,
            # cujo valor numérico é bem maior que len(keys)) — então NÃO se deve
            # usar len(keys) como limite, isso descartaria essas teclas. O
            # try/except é só defesa contra um 'keys' atípico vindo de um mock/stub
            # em teste, nunca deve disparar com o pygame real.
            try:
                return bool(keys[code])
            except (IndexError, TypeError):
                return False

        for p_idx, binding in enumerate(self.bindings):
            prefix = f"p{p_idx + 1}_"
            # --- teclado: sempre ativo, mesmo se o jogador também tiver um controle
            for action, code in binding.key_codes.items():
                if is_down(code):
                    new_held.add(prefix + action)
            # --- controle, se atribuído
            if binding.gamepad_slot is not None and self.gamepad.is_connected(binding.gamepad_slot):
                self._poll_gamepad(binding.gamepad_slot, prefix, new_held)

        # --- teclas globais (não específicas de jogador): pausa, reiniciar, etc.
        for name, code in (("escape", pygame.K_ESCAPE), ("r", pygame.K_r), ("m", pygame.K_m),
                           ("q", pygame.K_q), ("f11", pygame.K_F11), ("f", pygame.K_f),
                           ("up", pygame.K_UP), ("down", pygame.K_DOWN), ("left", pygame.K_LEFT),
                           ("right", pygame.K_RIGHT), ("return", pygame.K_RETURN), ("space", pygame.K_SPACE),
                           ("1", pygame.K_1), ("2", pygame.K_2), ("3", pygame.K_3), ("4", pygame.K_4)):
            if is_down(code):
                new_held.add("global_" + name)
        # pausa/confirma também via botão START/A de qualquer controle conectado
        for i in range(self.gamepad.count):
            if self.gamepad.is_connected(i):
                if self.gamepad.button_down(i, S.GAMEPAD_BUTTONS["pause"]):
                    new_held.add("global_escape")
                if self.gamepad.button_down(i, S.GAMEPAD_BUTTONS["confirm"]):
                    new_held.add("global_gp_confirm")
                if self.gamepad.button_down(i, S.GAMEPAD_BUTTONS["back"]):
                    new_held.add("global_gp_back")

        self.pressed |= (new_held - self.held)     # edge-trigger: entrou em held agora
        self.held = new_held

    def _poll_gamepad(self, slot, prefix, new_held):
        dx, dy = self.gamepad.axis_dir(slot, deadzone=S.JOYSTICK_DEADZONE)
        if dx < 0:
            new_held.add(prefix + "left")
        elif dx > 0:
            new_held.add(prefix + "right")

        btn = S.GAMEPAD_BUTTONS
        if self.gamepad.button_down(slot, btn["jump"]):
            new_held.add(prefix + "jump")
        if self.gamepad.button_down(slot, btn["dash"]):
            new_held.add(prefix + "dash")
        if self.gamepad.button_down(slot, btn["fire"]):
            new_held.add(prefix + "fire")

    def take_pressed(self):
        p = self.pressed
        self.pressed = set()
        return p

    def clear(self):
        self.held.clear()
        self.pressed.clear()

    # ------------------------------------------------------------ remapeamento de teclas/controle (menu)
    def rebind_key(self, player_idx, action, key_name):
        """Usado pela tela de configurações para trocar uma tecla (ex.: P1 'fire' de espaço para 'x').
        Aceita qualquer tecla reconhecida pelo pygame, não só as pré-cadastradas em _KEYMAP."""
        code = _resolve_key(key_name)
        self.bindings[player_idx].key_codes[action] = code

    def key_display(self, player_idx, action):
        """Nome de exibição da tecla de teclado atualmente mapeada para essa ação."""
        code = self.bindings[player_idx].key_codes.get(action)
        if code is None:
            return "—"
        return display_label(key_name_for_rebind(code))
