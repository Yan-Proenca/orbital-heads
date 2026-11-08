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
from gamepad import GamepadManager, PLAYSTATION

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
    if isinstance(name, str) and name.startswith("#") and name[1:].isdigit():
        return int(name[1:])            # tecla sem nome reconhecível: gravada como "#<codigo>"
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
    if len(name) == 3 and name[0] == "[" and name[2] == "]":      # teclado numérico: pygame chama de "[+]", "[-]"...
        return f"NUM {name[1]}"
    if len(name) == 1:
        return name.upper()
    return name.upper()


def default_pad_map():
    """Botões padrão do controle (nomes por POSIÇÃO no padrão Xbox: a = baixo, b = direita, x = esquerda, y = cima)."""
    return {action: S.GAMEPAD_BUTTONS[action] for action in S.PAD_ACTIONS}


def pad_device_for(family):
    """Perfil de botões usado por uma família de controle: PlayStation tem o seu, o resto (Xbox, Switch,
    genérico) usa o perfil 'xbox' — os botões são mapeados por posição, só os rótulos mudam."""
    return "playstation" if family == PLAYSTATION else "xbox"


def reserved_key_codes():
    return {_resolve_key(n) for n in S.RESERVED_KEYS}


class PlayerBinding:
    """Mapeamento de ações lógicas (left/right/jump/dash/fire/donate_life) de UM jogador:
    teclado (key_codes) e, para cada perfil de controle (xbox/playstation), pad_buttons[perfil][ação] = botão."""

    def __init__(self, key_names, gamepad_slot=None):
        self.key_codes = {action: _resolve_key(name) for action, name in key_names.items()}
        self.pad_buttons = {dev: default_pad_map() for dev in S.PAD_DEVICES}
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
                self._poll_gamepad(binding.gamepad_slot, prefix, new_held, binding)

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

    def _poll_gamepad(self, slot, prefix, new_held, binding=None):
        dx, dy = self.gamepad.axis_dir(slot, deadzone=S.JOYSTICK_DEADZONE)
        if dx < 0:
            new_held.add(prefix + "left")
        elif dx > 0:
            new_held.add(prefix + "right")

        # botões: perfil de botões do jogador para a família do controle conectado (Xbox x PlayStation)
        if binding is not None:
            buttons = binding.pad_buttons[pad_device_for(self.gamepad.family(slot))]
        else:
            buttons = default_pad_map()
        for action, button in buttons.items():
            if self.gamepad.button_down(slot, button):
                new_held.add(prefix + action)

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

    # ------------------------------------------------------------ remapeamento por jogador e dispositivo
    # device: "keyboard" | "xbox" | "playstation". Valores: keycode (teclado) ou nome de botão ("a", "lb"...).
    def binding_value(self, player_idx, device, action):
        b = self.bindings[player_idx]
        return b.key_codes.get(action) if device == "keyboard" else b.pad_buttons[device].get(action)

    def default_value(self, player_idx, device, action):
        if device == "keyboard":
            return _resolve_key(S.PLAYER_DEFS[player_idx]["key_names"][action])
        return default_pad_map().get(action)

    def is_customized(self, player_idx, device, action):
        return self.binding_value(player_idx, device, action) != self.default_value(player_idx, device, action)

    def is_bindable(self, device, value):
        """(ok, motivo): o valor pode ser atribuído a uma ação? Teclas reservadas e o botão START não podem."""
        if device == "keyboard":
            if value in reserved_key_codes():
                return False, "TECLA RESERVADA (" + key_name_for_rebind(value).upper() + ")"
            return True, ""
        if value == "start":
            return False, "START É RESERVADO PARA PAUSAR"
        if value not in S.PAD_BINDABLE:
            return False, "BOTÃO NÃO SUPORTADO"
        return True, ""

    def find_conflict(self, player_idx, device, action, value):
        """None se livre; ('self', outra_ação) se o MESMO jogador já usa o valor nesse dispositivo;
        ('player', outro_jogador, outra_ação) se OUTRO jogador usa a mesma tecla (só teclado)."""
        b = self.bindings[player_idx]
        table = b.key_codes if device == "keyboard" else b.pad_buttons[device]
        for other, v in table.items():
            if other != action and v == value:
                return ("self", other)
        if device == "keyboard":
            for i, ob in enumerate(self.bindings):
                if i != player_idx:
                    for other, v in ob.key_codes.items():
                        if v == value:
                            return ("player", i, other)
        return None

    def set_binding(self, player_idx, device, action, value):
        """Atribui sem checar conflito (quem chama decide: trocar, recusar...). Levanta ValueError se inválido."""
        ok, why = self.is_bindable(device, value)
        if not ok:
            raise ValueError(why)
        b = self.bindings[player_idx]
        if device == "keyboard":
            if action not in b.key_codes:
                raise ValueError("ação desconhecida: " + action)
            b.key_codes[action] = value
        else:
            if action not in S.PAD_ACTIONS:
                raise ValueError("ação fixa/desconhecida: " + action)
            b.pad_buttons[device][action] = value

    def swap_bindings(self, player_idx, device, action_a, action_b):
        """Troca os valores de duas ações do mesmo jogador/dispositivo (ninguém fica sem comando)."""
        b = self.bindings[player_idx]
        table = b.key_codes if device == "keyboard" else b.pad_buttons[device]
        table[action_a], table[action_b] = table[action_b], table[action_a]

    def rebind_pad(self, player_idx, device, action, button):
        self.set_binding(player_idx, device, action, button)

    def reset_device(self, player_idx, device):
        """Restaura os padrões de UM jogador em UM dispositivo (os outros ficam como estão). Se algum padrão
        de teclado colidir com a tecla personalizada de OUTRO jogador, não altera nada e devolve a lista de
        conflitos [(ação, outro_jogador, outra_ação)]; lista vazia = restaurado."""
        b = self.bindings[player_idx]
        if device == "keyboard":
            defaults = {a: _resolve_key(n) for a, n in S.PLAYER_DEFS[player_idx]["key_names"].items()}
            clashes = []
            for action, code in defaults.items():
                for i, ob in enumerate(self.bindings):
                    if i != player_idx:
                        for other, v in ob.key_codes.items():
                            if v == code:
                                clashes.append((action, i, other))
            if clashes:
                return clashes
            b.key_codes = defaults
        else:
            b.pad_buttons[device] = default_pad_map()
        return []

    # ------------------------------------------------------------ persistência (config.json)
    @staticmethod
    def _key_export_name(code):
        name = key_name_for_rebind(code)
        try:
            if _resolve_key(name) == code:
                return name
        except ValueError:
            pass
        return "#%d" % code                    # sem nome estável: grava o código

    def export_bindings(self):
        out = {}
        for i, b in enumerate(self.bindings):
            out[str(i + 1)] = {
                "keyboard": {a: self._key_export_name(c) for a, c in b.key_codes.items()},
                **{dev: dict(b.pad_buttons[dev]) for dev in S.PAD_DEVICES},
            }
        return out

    def import_bindings(self, data):
        """Aplica atalhos vindos do config.json. Tudo é validado: nome de tecla desconhecido, tecla reservada,
        botão inexistente, ação repetida ou tecla dividida entre jogadores são IGNORADOS (valem os padrões).
        Devolve a lista de avisos (vazia = tudo aproveitado)."""
        warns = []
        if not isinstance(data, dict):
            return warns
        reserved = reserved_key_codes()
        for i, b in enumerate(self.bindings):
            pd = data.get(str(i + 1))
            if not isinstance(pd, dict):
                continue
            tag = f"P{i + 1}"
            kb = pd.get("keyboard")
            if isinstance(kb, dict):
                new = dict(b.key_codes)
                for action, name in kb.items():
                    if action not in new:
                        warns.append(f"{tag} teclado: ação desconhecida '{action}'")
                        continue
                    try:
                        code = _resolve_key(name)
                    except ValueError:
                        warns.append(f"{tag} teclado: tecla desconhecida '{name}'")
                        continue
                    if code in reserved:
                        warns.append(f"{tag} teclado: tecla reservada '{name}'")
                        continue
                    new[action] = code
                if len(set(new.values())) != len(new):
                    warns.append(f"{tag} teclado: teclas repetidas, usando padrão")
                else:
                    b.key_codes = new
            for dev in S.PAD_DEVICES:
                pm = pd.get(dev)
                if not isinstance(pm, dict):
                    continue
                new = dict(b.pad_buttons[dev])
                for action, button in pm.items():
                    if action in S.PAD_ACTIONS and button in S.PAD_BINDABLE:
                        new[action] = button
                    else:
                        warns.append(f"{tag} {dev}: '{action}={button}' ignorado")
                if len(set(new.values())) != len(new):
                    warns.append(f"{tag} {dev}: botões repetidos, usando padrão")
                else:
                    b.pad_buttons[dev] = new
        self._resolve_cross_conflicts(warns)
        for w in warns:
            print("[config] controles:", w)
        return warns

    def _resolve_cross_conflicts(self, warns):
        """Duas pessoas nunca podem dividir a mesma tecla: se um config editado à mão causar isso, o jogador de
        número maior volta ao teclado padrão (e o outro também, se o padrão ainda colidir)."""
        n = len(self.bindings)
        for _ in range(n):
            clean = True
            for i in range(n):
                for j in range(i + 1, n):
                    if set(self.bindings[i].key_codes.values()) & set(self.bindings[j].key_codes.values()):
                        clean = False
                        for k in (j, i):
                            self.bindings[k].key_codes = {a: _resolve_key(nm) for a, nm in S.PLAYER_DEFS[k]["key_names"].items()}
                            warns.append(f"P{k + 1} teclado: tecla dividida com outro jogador, usando padrão")
                            if not set(self.bindings[i].key_codes.values()) & set(self.bindings[j].key_codes.values()):
                                break
            if clean:
                break
