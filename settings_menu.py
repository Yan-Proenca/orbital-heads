"""
settings_menu.py — menu avançado de CONFIGURAÇÕES (estado "settings" do Game).

Categorias na barra lateral:   ÁUDIO / VÍDEO  ·  CONTROLES  ·  VOLTAR

  ÁUDIO / VÍDEO   sliders de música e efeitos (0-100%, aplicados na hora), seletor de resolução (só modos que o
                  monitor suporta), botão APLICAR e checkbox de TELA CHEIA (troca sem reiniciar a partida).
  CONTROLES       jogador (P1-P4) × dispositivo (TECLADO / XBOX / PLAYSTATION): lista de ações com o comando atual,
                  remapeamento por captura ("PRESSIONE O NOVO BOTÃO"), conflitos com troca confirmada,
                  RESTAURAR PADRÕES com confirmação e associação de controle ao jogador.

Entrada: teclado (↑/↓ navega, ←/→ ajusta, ENTER seleciona, ESC volta), mouse (clicar, arrastar sliders, passar o
cursor) e controle (direcional/analógico + A confirma + B volta). Tudo que muda é salvo em config.json
(ver config.py) e aplicado ao AudioManager / InputManager / DisplayManager já existentes — este módulo só
desenha a interface e decide o que chamar; não reimplementa áudio, entrada nem vídeo.

Fluxo de navegação: foco na BARRA LATERAL (↑/↓ troca de categoria; ENTER ou → entra na categoria) ou no CONTEÚDO
(↑/↓ troca de linha; ←/→ ajusta o valor; ESC/B volta para a barra lateral; ESC na barra lateral fecha o menu).
"""
import math

import pygame

import gamepad as GP
import settings as S
from utils import clamp, draw_glow_circle, get_font, pulse

# paleta (a mesma dos outros menus do jogo)
CYAN, AMBER, GREEN, RED = (55, 197, 220), (255, 176, 74), (70, 240, 138), (255, 92, 110)
TEXT, MUTED, DIM = (225, 239, 245), (139, 172, 188), (96, 124, 140)
PANEL_FILL = (8, 18, 29)
WHITE_SOFT = (235, 248, 255)

TAB_AV, TAB_CONTROLS = 0, 1
SIDE_ITEMS = (("ÁUDIO / VÍDEO", "av"), ("CONTROLES", "controls"), ("VOLTAR", "back"))
AV_ROWS = ("music", "sfx", "res", "apply", "fs")
CONTROL_ROWS = ("player", "pad", "device") + tuple("act:" + a for a in S.CONTROL_ACTIONS) + ("restore",)
DEVICE_FAMILY = {"xbox": GP.XBOX, "playstation": GP.PLAYSTATION, "keyboard": GP.XBOX}
NAV_KEYS = ("global_up", "global_down", "global_left", "global_right", "global_return", "global_space",
            "global_gp_confirm", "global_gp_back")


def _lerp(a, b, t):
    t = clamp(t, 0.0, 1.0)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _level(volume):
    """Ondas do ícone de som: 0 = mudo, 1 = baixo, 2 = alto."""
    return 0 if volume <= 0 else (1 if volume < 50 else 2)


def _ease(t):
    return 1.0 - (1.0 - clamp(t, 0.0, 1.0)) ** 3


# ===================================================================== ícones e glifos (desenhados, sem imagens)
def draw_icon(surf, kind, cx, cy, color, level=2):
    """Ícones simples de 24 px: 'audio' (level 0 = mudo, 1-2 = ondas), 'video', 'controls', 'back'."""
    cx, cy = int(cx), int(cy)
    if kind == "audio":
        pygame.draw.rect(surf, color, (cx - 11, cy - 4, 6, 8))
        pygame.draw.polygon(surf, color, [(cx - 6, cy - 4), (cx + 2, cy - 10), (cx + 2, cy + 10), (cx - 6, cy + 4)])
        if level <= 0:
            pygame.draw.line(surf, RED, (cx + 5, cy - 5), (cx + 13, cy + 5), 2)
            pygame.draw.line(surf, RED, (cx + 13, cy - 5), (cx + 5, cy + 5), 2)
        else:
            for i in range(min(2, level)):
                pygame.draw.arc(surf, color, pygame.Rect(cx + 2 + i * 4, cy - 6 - i * 3, 10 + i * 3, 12 + i * 6), -0.9, 0.9, 2)
    elif kind == "video":
        pygame.draw.rect(surf, color, (cx - 12, cy - 9, 24, 15), width=2, border_radius=2)
        pygame.draw.line(surf, color, (cx, cy + 6), (cx, cy + 10), 2)
        pygame.draw.line(surf, color, (cx - 6, cy + 10), (cx + 6, cy + 10), 2)
        pygame.draw.line(surf, color, (cx - 8, cy + 2), (cx - 3, cy - 3), 1)
    elif kind == "controls":
        pygame.draw.rect(surf, color, (cx - 13, cy - 6, 26, 13), width=2, border_radius=6)
        pygame.draw.line(surf, color, (cx - 8, cy - 2), (cx - 8, cy + 4), 2)
        pygame.draw.line(surf, color, (cx - 11, cy + 1), (cx - 5, cy + 1), 2)
        pygame.draw.circle(surf, color, (cx + 6, cy - 1), 2)
        pygame.draw.circle(surf, color, (cx + 10, cy + 3), 2)
    elif kind == "back":
        pygame.draw.polygon(surf, color, [(cx - 11, cy), (cx - 2, cy - 8), (cx - 2, cy - 3), (cx + 10, cy - 3),
                                           (cx + 10, cy + 3), (cx - 2, cy + 3), (cx - 2, cy + 8)])


def draw_pad_glyph(surf, center, name, family, r=15):
    """Botão de controle como o jogador o vê no controle dele: letras coloridas no Xbox, ✕ ○ □ △ desenhados
    no PlayStation (formas, não texto: não dependem da fonte) e pílulas para ombros/BACK. Devolve a largura."""
    x, y = int(center[0]), int(center[1])
    name = name.lower()
    col = S.hx(GP.button_color(name, family))
    if name in ("a", "b", "x", "y"):
        if family == GP.PLAYSTATION:
            pygame.draw.circle(surf, (14, 24, 34), (x, y), r)
            pygame.draw.circle(surf, col, (x, y), r, width=2)
            k = int(r * 0.45)
            if name == "a":
                pygame.draw.line(surf, col, (x - k, y - k), (x + k, y + k), 3)
                pygame.draw.line(surf, col, (x + k, y - k), (x - k, y + k), 3)
            elif name == "b":
                pygame.draw.circle(surf, col, (x, y), k + 1, width=3)
            elif name == "x":
                pygame.draw.rect(surf, col, (x - k, y - k, 2 * k, 2 * k), width=3)
            else:
                pygame.draw.polygon(surf, col, [(x, y - k - 1), (x + k + 1, y + k), (x - k - 1, y + k)], width=3)
        else:
            pygame.draw.circle(surf, col, (x, y), r)
            pygame.draw.circle(surf, (14, 22, 30), (x, y), r, width=2)
            txt = get_font(S.FONT_UI_NAME, int(r * 1.15), bold=True).render(GP.button_label(name, family), True, (14, 22, 30))
            surf.blit(txt, txt.get_rect(center=(x, y)))
        return r * 2
    label = GP.button_label(name, family)
    font = get_font(S.FONT_UI_NAME, 13, bold=True)
    txt = font.render(label, True, (235, 245, 250))
    w = max(2 * r + 6, txt.get_width() + 18)
    rect = pygame.Rect(0, 0, w, int(r * 1.5))
    rect.center = (x, y)
    pygame.draw.rect(surf, (24, 44, 60), rect, border_radius=rect.height // 2)
    pygame.draw.rect(surf, col, rect, width=2, border_radius=rect.height // 2)
    surf.blit(txt, txt.get_rect(center=rect.center))
    return w


def draw_keycap(surf, rect, label, accent=(65, 101, 120), fill=(19, 34, 46), color=(240, 240, 250)):
    pygame.draw.rect(surf, (4, 9, 15), rect.move(0, 3), border_radius=8)
    pygame.draw.rect(surf, fill, rect, border_radius=8)
    pygame.draw.rect(surf, accent, rect, width=2, border_radius=8)
    font = get_font(S.FONT_UI_NAME, 17, bold=True)
    txt = font.render(label, True, color)
    surf.blit(txt, txt.get_rect(center=rect.center))


class SettingsMenu:
    def __init__(self, game):
        self.game = game
        self.return_to = "paused"
        self.tab = TAB_AV
        self.side_sel = 0
        self.focus = "side"
        self.row = 0
        self.t_open = 1.0
        self.tab_anim = 1.0
        self.tab_dir = 1
        self.c_player = 0
        self.c_device = "keyboard"
        self.res_list, self.res_idx = [], 0
        self.capture = None            # dict(player, device, action, t, msg, msg_t)
        self.modal = None              # dict(kind, title, lines, buttons, sel, data)
        self.toast = ("", MUTED)
        self.toast_t = 0.0
        self.drag = None
        self._save_t = 0.0
        self._swallow = False
        self._hl = {}
        self._hit, self._mhit, self._tracks = [], [], {}
        self._origin = (0, 0)
        self._sfx_prev_t = 0.0
        self._dim = pygame.Surface((S.WIDTH, S.HEIGHT))
        self._dim.fill((2, 6, 12))
        self.panel = pygame.Rect(0, 0, 1060, 620)
        self.panel.center = (S.WIDTH // 2, S.HEIGHT // 2)
        self._content_size = (self.panel.width - 286 - 26, self.panel.height - 92 - 50)
        self._buf = pygame.Surface(self._content_size, pygame.SRCALPHA)

    # ------------------------------------------------------------ abrir / fechar
    def open(self, return_to="paused", tab=TAB_AV):
        g = self.game
        self.return_to = return_to
        self.tab, self.side_sel, self.focus, self.row = tab, tab, "side", 0
        self.t_open, self.tab_anim = 0.0, 1.0
        self.capture = self.modal = self.drag = None
        self._swallow = False
        self.toast_t = 0.0
        self.c_player = 0
        self._sync_device_to_pad()
        self._refresh_resolutions()
        g.state = "settings"
        g.menu.reset_hover()
        g.input.text_input_active = False

    def close(self):
        g = self.game
        g.config.save()                     # só grava se algo mudou (ConfigManager compara)
        self.capture = self.modal = self.drag = None
        g.input.text_input_active = False
        g.state = self.return_to
        g.menu.reset_hover()

    # ------------------------------------------------------------ helpers de estado
    def rows(self):
        return AV_ROWS if self.tab == TAB_AV else CONTROL_ROWS

    def _say(self, text, color=MUTED, secs=2.6):
        self.toast, self.toast_t = (text, color), secs

    def _refresh_resolutions(self):
        d = self.game.display
        if d is None:
            self.res_list, self.res_idx = [(S.WIDTH, S.HEIGHT)], 0
            return
        self.res_list = d.available_resolutions(d.fullscreen)
        cur = d.size if d.size in self.res_list else d.nearest(d.size, d.fullscreen)
        self.res_idx = self.res_list.index(cur) if cur in self.res_list else 0

    def _sync_device_to_pad(self):
        inp = self.game.input
        slot = inp.bindings[self.c_player].gamepad_slot
        if slot is not None and inp.gamepad.is_connected(slot):
            self.c_device = "playstation" if inp.gamepad.family(slot) == GP.PLAYSTATION else "xbox"
        else:
            self.c_device = "keyboard"

    def _pad_options(self):
        gp = self.game.input.gamepad
        return [None] + [i for i in range(gp.count) if gp.is_connected(i)]

    def _switch_tab(self, tab):
        if tab != self.tab:
            self.tab_dir = 1 if tab > self.tab else -1
            self.tab = tab
            self.tab_anim = 0.0
            self.row = 0
            self.game.audio.on_menu_move()

    # ------------------------------------------------------------ áudio
    def _volume(self, which):
        a = self.game.audio
        return a.music_percent if which == "music" else a.sfx_percent

    def _set_volume(self, which, value, preview=True):
        g, a = self.game, self.game.audio
        value = int(clamp(value, 0, 100))
        if value == self._volume(which):
            return
        if which == "music":
            a.set_music_volume(value / 100.0)
            if value > 0 and not a.music_enabled:
                a.toggle_music()            # mexeu no slider: religa a trilha (o toggle do menu de pausa continua existindo)
            g.config.set_audio(music=value)
        else:
            a.set_sfx_volume(value / 100.0)
            if value > 0 and not a.sfx_enabled:
                a.sfx_enabled = True
            g.config.set_audio(sfx=value)
            if preview:
                a.play_sfx("shoot", cooldown=0.12)       # ouve-se o efeito enquanto arrasta
        self._save_t = 0.6                                # grava quando parar de mexer

    # ------------------------------------------------------------ vídeo
    def _apply_video(self, fullscreen=None):
        g = self.game
        if g.display is None:
            self._say("VÍDEO INDISPONÍVEL NESTA EXECUÇÃO", AMBER)
            return
        fs = g.display.fullscreen if fullscreen is None else fullscreen
        size = self.res_list[self.res_idx]
        res = g.apply_video(size, fs)
        self._refresh_resolutions()
        if res["note"]:
            self._say(res["note"], AMBER, 4.0)
        else:
            self._say(f"{res['size'][0]}×{res['size'][1]} · {'TELA CHEIA' if res['fullscreen'] else 'JANELA'} APLICADO", GREEN)
        g.audio.on_menu_confirm()

    # ------------------------------------------------------------ controles
    def _after_controls_change(self):
        g = self.game
        g.config.set_controls(g.input.export_bindings())
        g.config.save()
        g.audio.on_menu_confirm()

    def _action_name(self, action):
        return S.CONTROL_LABELS[action]

    def _value_text(self, device, value):
        if device == "keyboard":
            from input_handler import key_name_for_rebind, display_label
            return display_label(key_name_for_rebind(value))
        return GP.button_label(value, DEVICE_FAMILY[device])

    def _start_capture(self, action):
        g, inp = self.game, self.game.input
        dev = self.c_device
        if dev != "keyboard":
            if action not in S.PAD_ACTIONS:
                self._say("MOVIMENTO É FIXO NO DIRECIONAL / ANALÓGICO ESQUERDO", AMBER)
                return
            if not any(inp.gamepad.is_connected(i) for i in range(inp.gamepad.count)):
                self._say("CONECTE UM CONTROLE PARA REMAPEAR OS BOTÕES", AMBER)
                return
        self.capture = dict(player=self.c_player, device=dev, action=action, t=S.CAPTURE_TIMEOUT, msg="", msg_t=0.0)
        inp.text_input_active = True
        inp.last_key_pressed = None
        inp.last_gamepad_button = None
        g.audio.on_menu_confirm()

    def _end_capture(self, text=None, color=MUTED):
        self.capture = None
        self.game.input.text_input_active = False
        self.game.input.last_key_pressed = None
        self.game.input.last_gamepad_button = None
        self._swallow = True               # a tecla/botão que acabou de ser pressionado não deve navegar o menu
        if text:
            self._say(text, color)

    def _update_capture(self, dt):
        g, inp, m = self.game, self.game.input, self.game.menu
        c = self.capture
        c["t"] -= dt
        c["msg_t"] = max(0.0, c["msg_t"] - dt)
        cancel_click = m.click_pos is not None and self._mhit_at(m.click_pos) == "cancel"
        if "global_escape" in g.just or m.right_clicked or cancel_click:       # ESC, START do controle ou clique direito
            self._end_capture("REMAPEAMENTO CANCELADO", AMBER)
            return
        if c["t"] <= 0:
            self._end_capture("TEMPO ESGOTADO — NADA FOI ALTERADO", AMBER)
            return
        dev = c["device"]
        gp = inp.gamepad
        if dev != "keyboard" and not any(gp.is_connected(i) for i in range(gp.count)):
            self._end_capture("CONTROLE DESCONECTADO — REMAPEAMENTO CANCELADO", AMBER)
            return
        if dev == "keyboard":
            inp.last_gamepad_button = None
            key = inp.last_key_pressed
            if key is None:
                return
            inp.last_key_pressed = None
            self._try_assign(key)
        else:
            inp.last_key_pressed = None
            hit = inp.last_gamepad_button
            if hit is None:
                return
            inp.last_gamepad_button = None
            slot, name = hit
            b = inp.bindings[c["player"]]
            if b.gamepad_slot is not None and gp.is_connected(b.gamepad_slot) and slot != b.gamepad_slot:
                c["msg"], c["msg_t"] = "USE O CONTROLE ASSOCIADO A ESTE JOGADOR", 2.5
                return
            if b.gamepad_slot is None:
                inp.assign_gamepad(c["player"], slot)           # 1º botão apertado associa o controle ao jogador
            self._try_assign(name)

    def _try_assign(self, value):
        inp = self.game.input
        c = self.capture
        p, dev, action = c["player"], c["device"], c["action"]
        ok, why = inp.is_bindable(dev, value)
        if not ok:
            c["msg"], c["msg_t"] = why, 2.8
            return
        if value == inp.binding_value(p, dev, action):
            self._end_capture("MESMO COMANDO — NADA FOI ALTERADO")
            return
        conflict = inp.find_conflict(p, dev, action, value)
        if conflict is None:
            inp.set_binding(p, dev, action, value)
            self._end_capture(f"{self._action_name(action)} → {self._value_text(dev, value)}", GREEN)
            self._after_controls_change()
        elif conflict[0] == "player":
            c["msg"] = f"JÁ USADA POR P{conflict[1] + 1} ({self._action_name(conflict[2])})"
            c["msg_t"] = 3.2
        else:
            other = conflict[1]
            self._end_capture()
            self.modal = dict(kind="swap", title="COMANDO JÁ ATRIBUÍDO", sel=0,
                              lines=[f"«{self._value_text(dev, value)}» já é usado em {self._action_name(other)}.",
                                     f"TROCAR: {self._action_name(action)} recebe «{self._value_text(dev, value)}» e",
                                     f"{self._action_name(other)} fica com «{self._value_text(dev, inp.binding_value(p, dev, action))}»."],
                              buttons=[("TROCAR", "swap"), ("CANCELAR", "cancel")], data=(p, dev, action, other))

    def _ask_restore(self):
        p, dev = self.c_player, self.c_device
        self.modal = dict(kind="restore", title="RESTAURAR PADRÕES", sel=1,
                          lines=[f"Voltar os comandos de {S.PLAYER_DEFS[p]['short']} ({S.CONTROL_DEVICE_LABELS[dev]})",
                                 "para o padrão original? Os outros dispositivos e jogadores não mudam."],
                          buttons=[("RESTAURAR", "restore"), ("CANCELAR", "cancel")], data=(p, dev))

    def _update_modal(self):
        g, m = self.game, self.game.menu
        md = self.modal
        navh = m.nav_delta_h()
        if navh:
            md["sel"] = (md["sel"] + navh) % len(md["buttons"])
            g.audio.on_menu_move()
        choice = None
        if m.click_pos is not None:
            hit = self._mhit_at(m.click_pos)
            if isinstance(hit, int):
                choice = md["buttons"][hit][1]
        if m.mouse_moved:
            hit = self._mhit_at(m.mouse_pos)
            if isinstance(hit, int):
                md["sel"] = hit
        if choice is None and ("global_return" in g.just or "global_space" in g.just or "global_gp_confirm" in g.just):
            choice = md["buttons"][md["sel"]][1]
        if choice is None and ("global_escape" in g.just or "global_gp_back" in g.just or m.right_clicked):
            choice = "cancel"
        if choice is None:
            return
        self.modal = None
        self._swallow = True
        if choice == "cancel":
            g.audio.on_menu_move()
            return
        if choice == "swap":
            p, dev, action, other = md["data"]
            g.input.swap_bindings(p, dev, action, other)
            self._say(f"{self._action_name(action)} ⇄ {self._action_name(other)} TROCADOS", GREEN)
            self._after_controls_change()
        elif choice == "restore":
            p, dev = md["data"]
            clashes = g.input.reset_device(p, dev)
            if clashes:
                act, op, oact = clashes[0]
                self._say(f"PADRÃO COLIDE COM P{op + 1} ({self._action_name(oact)}) — ALTERE UM DOS DOIS", AMBER, 4.0)
            else:
                self._say("PADRÕES RESTAURADOS", GREEN)
                self._after_controls_change()

    # ------------------------------------------------------------ ajustar / ativar linhas
    def _adjust(self, rid, d):
        """←/→ numa linha. Devolve True se a linha é ajustável (senão ← volta para a barra lateral)."""
        g = self.game
        if rid in ("music", "sfx"):
            self._set_volume(rid, self._volume(rid) + d * S.VOLUME_STEP)
            return True
        if rid == "res":
            if self.res_list:
                self.res_idx = int(clamp(self.res_idx + d, 0, len(self.res_list) - 1))
                g.audio.on_menu_move()
            return True
        if rid == "player":
            self.c_player = (self.c_player + d) % S.MAX_PLAYERS
            self._sync_device_to_pad()
            g.audio.on_menu_move()
            return True
        if rid == "device":
            i = S.CONTROL_DEVICES.index(self.c_device)
            self.c_device = S.CONTROL_DEVICES[(i + d) % len(S.CONTROL_DEVICES)]
            g.audio.on_menu_move()
            return True
        if rid == "pad":
            opts = self._pad_options()
            cur = g.input.bindings[self.c_player].gamepad_slot
            i = opts.index(cur) if cur in opts else 0
            g.input.assign_gamepad(self.c_player, opts[(i + d) % len(opts)])
            self._sync_device_to_pad()
            g.audio.on_menu_move()
            return True
        return False

    def _activate(self, rid):
        g = self.game
        if rid in ("res", "apply"):
            self._apply_video()
        elif rid == "fs":
            self._apply_video(fullscreen=not (g.display.fullscreen if g.display else False))
        elif rid in ("player", "pad", "device"):
            self._adjust(rid, 1)
        elif rid.startswith("act:"):
            self._start_capture(rid[4:])
        elif rid == "restore":
            self._ask_restore()

    # ------------------------------------------------------------ atualização por quadro
    def update(self, dt):
        g = self.game
        self.t_open = min(1.0, self.t_open + dt / 0.22)
        self.tab_anim = min(1.0, self.tab_anim + dt / 0.18)
        self.toast_t = max(0.0, self.toast_t - dt)
        if self._save_t > 0:
            self._save_t -= dt
            if self._save_t <= 0:
                g.config.save()
        self._animate_highlights(dt)
        if self.modal is not None:
            self._update_modal()
            return
        if self.capture is not None:
            self._update_capture(dt)
            return
        if self._swallow:                              # espera soltar o botão que fechou a captura/modal
            if not (set(NAV_KEYS) & g.input.held):
                self._swallow = False
            return
        self._handle_mouse()
        self._handle_keys()

    def _animate_highlights(self, dt):
        want = {}
        for i in range(len(SIDE_ITEMS)):
            want[f"side:{i}"] = 1.0 if (self.focus == "side" and self.side_sel == i) else (0.45 if (i == self.tab and i < 2) else 0.0)
        rows = self.rows()
        for i, rid in enumerate(rows):
            want[f"row:{rid}"] = 1.0 if (self.focus == "main" and self.row == i) else 0.0
        k = min(1.0, 14.0 * dt)
        for key, tgt in want.items():
            cur = self._hl.get(key, 0.0)
            self._hl[key] = cur + (tgt - cur) * k

    def _handle_mouse(self):
        g, m = self.game, self.game.menu
        if self.drag:
            if m.mouse_down:
                self._drag_to(m.mouse_pos[0])
            else:
                self.drag = None
                g.config.save()
                g.audio.on_menu_confirm()
        if m.mouse_moved and not self.drag:
            hit = self._hit_at(m.mouse_pos)
            if hit:
                kind, arg = hit
                if kind == "side":
                    self.focus, self.side_sel = "side", arg
                elif kind == "row" and arg in self.rows():
                    self.focus, self.row = "main", self.rows().index(arg)
                elif kind in ("slider", "arrow", "seg", "check", "button") and arg is not None:
                    rid = arg[0] if isinstance(arg, tuple) else arg
                    if rid in self.rows():
                        self.focus, self.row = "main", self.rows().index(rid)
        if m.click_pos is not None:
            self._click(m.click_pos)
        if m.right_clicked:
            self._back()

    def _drag_to(self, x):
        tr = self._tracks.get(self.drag)
        if tr is not None:
            self._set_volume(self.drag, (x - tr.left) / max(1, tr.width) * 100.0)

    def _click(self, pos):
        g = self.game
        hit = self._hit_at(pos)
        if not hit:
            return
        kind, arg = hit
        if kind == "side":
            self.side_sel = arg
            if arg == 2:
                g.audio.on_menu_confirm()
                self.close()
            else:
                self._switch_tab(arg)
                self.focus = "main"
                self.row = 0
            return
        rid = arg[0] if isinstance(arg, tuple) else arg
        if rid in self.rows():
            self.focus, self.row = "main", self.rows().index(rid)
        if kind == "slider":
            self.drag = arg
            self._drag_to(pos[0])
        elif kind == "arrow":
            self._adjust(arg[0], arg[1])
        elif kind == "seg":
            rid, idx = arg
            if rid == "player":
                self.c_player = idx
                self._sync_device_to_pad()
            elif rid == "device":
                self.c_device = S.CONTROL_DEVICES[idx]
            g.audio.on_menu_move()
        elif kind in ("check", "button"):
            self._activate(rid)
        elif kind == "row" and (rid.startswith("act:") or rid in ("restore", "apply", "fs")):
            self._activate(rid)

    def _back(self):
        if self.focus == "main":
            self.focus = "side"
            self.game.audio.on_menu_move()
        else:
            self.game.audio.on_menu_confirm()
            self.close()

    def _handle_keys(self):
        g, m = self.game, self.game.menu
        nav, navh = m.nav_delta(), m.nav_delta_h()
        confirm = m.click_pos is None and ("global_return" in g.just or "global_space" in g.just or "global_gp_confirm" in g.just)
        back = "global_escape" in g.just or "global_gp_back" in g.just
        if self.focus == "side":
            if nav:
                self.side_sel = (self.side_sel + nav) % len(SIDE_ITEMS)
                if self.side_sel < 2:
                    self._switch_tab(self.side_sel)
                else:
                    g.audio.on_menu_move()
            if confirm or navh > 0:
                if self.side_sel == 2:
                    if confirm:
                        g.audio.on_menu_confirm()
                        self.close()
                else:
                    self.focus, self.row = "main", 0
                    g.audio.on_menu_move()
            elif back:
                g.audio.on_menu_confirm()
                self.close()
            return
        rows = self.rows()
        if nav:
            self.row = (self.row + nav) % len(rows)
            g.audio.on_menu_move()
        if navh:
            if not self._adjust(rows[self.row], navh) and navh < 0:
                self.focus = "side"
                g.audio.on_menu_move()
        if confirm:
            self._activate(rows[self.row])
        elif back:
            self.focus = "side"
            g.audio.on_menu_move()

    # ------------------------------------------------------------ hit testing
    def _reg(self, rect, kind, arg=None):
        self._hit.append((rect.move(self._origin), kind, arg))

    def _hit_at(self, pos):
        for rect, kind, arg in reversed(self._hit):
            if rect.collidepoint(pos):
                return kind, arg
        return None

    def _mhit_at(self, pos):
        for rect, ident in reversed(self._mhit):
            if rect.collidepoint(pos):
                return ident
        return None

    # =====================================================================  DESENHO
    def draw(self, surf):
        g = self.game
        ease = _ease(self.t_open)
        dy = int((1.0 - ease) * 34)
        self._dim.set_alpha(int(205 * ease))
        surf.blit(self._dim, (0, 0))
        panel = self.panel.move(0, dy)
        g._draw_sci_panel(surf, panel, accent=CYAN, fill=PANEL_FILL, radius=14, border=3)
        self._hit, self._mhit = [], []
        self._origin = (0, 0)

        title = get_font(S.FONT_TITLE_NAME, 36).render("CONFIGURAÇÕES", True, TEXT)
        surf.blit(title, (panel.left + 30, panel.top + 20))
        sub = get_font(S.FONT_UI_NAME, 13, bold=True).render("CENTRAL DE AJUSTES // ÁUDIO · VÍDEO · CONTROLES", True, (107, 153, 172))
        surf.blit(sub, sub.get_rect(midright=(panel.right - 30, panel.top + 42)))
        pygame.draw.line(surf, (45, 116, 137), (panel.left + 28, panel.top + 74), (panel.right - 28, panel.top + 74), 1)

        self._draw_sidebar(surf, panel)
        content = pygame.Rect(panel.left + 286, panel.top + 92, *self._content_size)
        pygame.draw.line(surf, (36, 62, 78), (panel.left + 272, panel.top + 92), (panel.left + 272, panel.bottom - 40), 1)
        self._draw_content(surf, content)

        hint = self._hint_text()
        h = get_font(S.FONT_UI_NAME, 14).render(hint, True, (115, 148, 165))
        surf.blit(h, h.get_rect(midbottom=(panel.centerx, panel.bottom - 12)))

        if self.toast_t > 0 and self.toast[0]:
            self._draw_toast(surf, content)
        if self.capture is not None:
            self._draw_capture(surf)
        if self.modal is not None:
            self._draw_modal(surf)
        g.menu.draw_cursor(surf)

    def _hint_text(self):
        if self.capture is not None:
            return "ESC · START · CLIQUE DIREITO CANCELAM"
        if self.modal is not None:
            return "←/→ ESCOLHE · ENTER CONFIRMA · ESC CANCELA"
        if self.focus == "side":
            return "↑/↓ CATEGORIA · ENTER OU → ABRE · ESC FECHA"
        return "↑/↓ OPÇÃO · ←/→ AJUSTA · ENTER SELECIONA · ESC VOLTA ÀS CATEGORIAS"

    def _draw_toast(self, surf, content):
        text, col = self.toast
        font = get_font(S.FONT_UI_NAME, 16, bold=True)
        img = font.render(text, True, col)
        box = img.get_rect().inflate(30, 14)
        box.midbottom = (content.centerx, content.bottom + 8)
        a = clamp(self.toast_t / 0.4, 0.0, 1.0)
        pygame.draw.rect(surf, _lerp(PANEL_FILL, (14, 28, 40), a), box, border_radius=8)
        pygame.draw.rect(surf, _lerp(PANEL_FILL, col, a), box, width=1, border_radius=8)
        surf.blit(img, img.get_rect(center=box.center))

    # ------------------------------------------------------------ barra lateral
    def _draw_sidebar(self, surf, panel):
        icons = ("video", "controls", "back")
        for i, (label, _) in enumerate(SIDE_ITEMS):
            if i < 2:
                rect = pygame.Rect(panel.left + 28, panel.top + 104 + i * 72, 232, 60)
            else:
                rect = pygame.Rect(panel.left + 28, panel.bottom - 48 - 60, 232, 60)
            a = self._hl.get(f"side:{i}", 0.0)
            active = i == self.tab and i < 2
            accent = AMBER if i == 2 else CYAN
            pygame.draw.rect(surf, (4, 9, 15), rect.move(0, 3), border_radius=8)
            pygame.draw.rect(surf, _lerp((11, 24, 36), (25, 46, 60), a), rect, border_radius=8)
            pygame.draw.rect(surf, _lerp((42, 63, 77), accent, max(a, 0.55 if active else 0.0)), rect,
                             width=2 if (a > 0.5 or active) else 1, border_radius=8)
            if a > 0.05 or active:
                pygame.draw.rect(surf, accent, (rect.left + 7, rect.top + 10, 4, rect.height - 20), border_radius=2)
            if a > 0.4:
                draw_glow_circle(surf, rect.left + 38, rect.centery, 34, accent, intensity=0.28 * a, layers=3)
            col = _lerp((150, 176, 190), accent if i == 2 else TEXT, max(a, 0.8 if active else 0.0))
            if i == 0:
                level = 2 if self.game.audio.music_percent > 0 or self.game.audio.sfx_percent > 0 else 0
                draw_icon(surf, "audio", rect.left + 28, rect.centery, col, level)
                draw_icon(surf, "video", rect.left + 62, rect.centery, col)
                lab_x = rect.left + 90
            else:
                draw_icon(surf, icons[i], rect.left + 38, rect.centery, col)
                lab_x = rect.left + 66
            txt = get_font(S.FONT_UI_NAME, 17 if i == 0 else 20, bold=True).render(label, True, col)
            surf.blit(txt, txt.get_rect(midleft=(lab_x, rect.centery)))
            self._hit.append((rect.inflate(6, 4), "side", i))

    # ------------------------------------------------------------ conteúdo (desenhado num buffer próprio)
    def _draw_content(self, surf, content):
        buf = self._buf
        buf.fill((0, 0, 0, 0))
        anim = _ease(self.tab_anim)
        ox = int((1.0 - anim) * 46 * self.tab_dir)
        self._origin = (content.left + ox, content.top)
        self._tracks = {}
        if self.tab == TAB_AV:
            self._draw_av(buf)
        else:
            self._draw_controls(buf)
        buf.set_alpha(int(255 * (0.25 + 0.75 * anim)))
        surf.blit(buf, (content.left + ox, content.top))

    def _row_frame(self, buf, rect, rid):
        a = self._hl.get(f"row:{rid}", 0.0)
        pygame.draw.rect(buf, _lerp((9, 20, 31), (20, 40, 54), a), rect, border_radius=8)
        pygame.draw.rect(buf, _lerp((34, 56, 70), CYAN, a), rect, width=2 if a > 0.5 else 1, border_radius=8)
        if a > 0.05:
            pygame.draw.rect(buf, _lerp((9, 20, 31), CYAN, a), (rect.left + 5, rect.top + 9, 4, rect.height - 18), border_radius=2)
        self._reg(rect, "row", rid)
        return a

    def _label(self, buf, text, pos, size=19, color=TEXT, bold=True, anchor="midleft"):
        img = get_font(S.FONT_UI_NAME, size, bold=bold).render(text, True, color)
        buf.blit(img, img.get_rect(**{anchor: pos}))
        return img

    def _section(self, buf, y, text, icon):
        draw_icon(buf, icon, 14, y + 12, CYAN)
        self._label(buf, text, (38, y + 12), 17, CYAN)
        pygame.draw.line(buf, (36, 62, 78), (38 + 14 * len(text) + 8, y + 12), (self._content_size[0] - 4, y + 12), 1)

    def _draw_slider(self, buf, rid, label, y, value, color, icon_level):
        cw = self._content_size[0]
        rect = pygame.Rect(0, y, cw, 60)
        a = self._row_frame(buf, rect, rid)
        draw_icon(buf, "audio", 28, y + 30, _lerp(MUTED, TEXT, a), icon_level)
        self._label(buf, label, (62, y + 30), 19, TEXT)
        track = pygame.Rect(230, y + 24, cw - 230 - 120, 12)
        self._tracks[rid] = track.move(self._origin)
        pygame.draw.rect(buf, (6, 14, 22), track, border_radius=6)
        pygame.draw.rect(buf, (40, 68, 84), track, width=1, border_radius=6)
        fill_w = int(track.width * value / 100)
        if fill_w > 0:
            dark = _lerp(color, (8, 16, 24), 0.55)
            pygame.draw.rect(buf, dark, (track.left, track.top, fill_w, track.height), border_radius=6)
            pygame.draw.rect(buf, color, (track.left + 1, track.top + 2, max(0, fill_w - 2), 4), border_radius=3)
        for pct in (0, 25, 50, 75, 100):
            tx = track.left + int(track.width * pct / 100)
            pygame.draw.line(buf, (60, 90, 106), (tx, track.bottom + 4), (tx, track.bottom + 8), 1)
        kx = track.left + fill_w
        draw_glow_circle(buf, kx, track.centery, 22 + 4 * a, color, intensity=0.35 + 0.35 * a + (0.2 if self.drag == rid else 0), layers=3)
        pygame.draw.circle(buf, (6, 12, 20), (kx, track.centery), 11)
        pygame.draw.circle(buf, color, (kx, track.centery), 11, width=3)
        pygame.draw.circle(buf, WHITE_SOFT, (kx, track.centery), 4)
        pct_img = get_font(S.FONT_UI_NAME, 24, bold=True).render(f"{value}%", True, TEXT if value > 0 else AMBER)
        buf.blit(pct_img, pct_img.get_rect(midright=(cw - 22, y + 27)))
        if value == 0:
            mute = get_font(S.FONT_UI_NAME, 12, bold=True).render("MUDO", True, AMBER)
            buf.blit(mute, mute.get_rect(midright=(cw - 22, y + 48)))
        self._reg(track.inflate(26, 34), "slider", rid)

    def _draw_av(self, buf):
        cw = self._content_size[0]
        aud = self.game.audio
        self._section(buf, 0, "ÁUDIO", "audio")
        self._draw_slider(buf, "music", "MÚSICA", 34, aud.music_percent, CYAN, _level(aud.music_percent))
        self._draw_slider(buf, "sfx", "EFEITOS", 102, aud.sfx_percent, AMBER, _level(aud.sfx_percent))
        self._section(buf, 182, "VÍDEO", "video")
        d = self.game.display

        # --- resolução (seletor ◄ valor ►)
        rect = pygame.Rect(0, 216, cw, 56)
        a_row = self._row_frame(buf, rect, "res")
        self._label(buf, "RESOLUÇÃO", (24, rect.centery), 19)
        size = self.res_list[self.res_idx] if self.res_list else (S.WIDTH, S.HEIGHT)
        left = pygame.Rect(230, rect.centery - 18, 36, 36)
        box = pygame.Rect(274, rect.centery - 19, 200, 38)
        right = pygame.Rect(482, rect.centery - 18, 36, 36)
        for r, d_, ok in ((left, -1, self.res_idx > 0), (right, 1, self.res_idx < len(self.res_list) - 1)):
            pygame.draw.rect(buf, (19, 34, 46) if ok else (11, 20, 28), r, border_radius=7)
            pygame.draw.rect(buf, CYAN if ok else (40, 58, 70), r, width=2, border_radius=7)
            cx, cy = r.center
            pts = [(cx + 5, cy - 8), (cx - 5, cy), (cx + 5, cy + 8)] if d_ < 0 else [(cx - 5, cy - 8), (cx + 5, cy), (cx - 5, cy + 8)]
            pygame.draw.polygon(buf, TEXT if ok else (60, 80, 92), pts)
            self._reg(r, "arrow", ("res", d_))
        pygame.draw.rect(buf, (6, 14, 22), box, border_radius=7)
        pygame.draw.rect(buf, _lerp((50, 82, 98), CYAN, a_row), box, width=2, border_radius=7)
        self._label(buf, f"{size[0]} × {size[1]}", box.center, 20, TEXT, anchor="center")
        cur = d.size if d else (S.WIDTH, S.HEIGHT)
        tag, tcol = ("ATUAL", GREEN) if size == cur else ("PENDENTE", AMBER)
        self._label(buf, tag, (532, rect.centery), 14, tcol)

        # --- aplicar
        rect = pygame.Rect(0, 280, cw, 48)
        a_row = self._row_frame(buf, rect, "apply")
        pending = size != cur
        btn = pygame.Rect(230, rect.centery - 18, 288, 36)
        pygame.draw.rect(buf, (20, 62, 44) if pending else (14, 26, 36), btn, border_radius=8)
        pygame.draw.rect(buf, GREEN if pending else (46, 70, 82), btn, width=2, border_radius=8)
        if pending and a_row > 0.2:
            draw_glow_circle(buf, btn.centerx, btn.centery, 70, GREEN, intensity=0.18 * a_row, layers=3)
        self._label(buf, "APLICAR RESOLUÇÃO" if pending else "RESOLUÇÃO APLICADA", btn.center, 17,
                    (210, 255, 225) if pending else DIM, anchor="center")
        self._reg(btn, "button", "apply")
        mode = "TELA CHEIA" if (d and d.fullscreen) else "JANELA"
        self._label(buf, f"{cur[0]}×{cur[1]} · {mode}", (cw - 22, rect.centery), 14, MUTED, anchor="midright")

        # --- tela cheia
        rect = pygame.Rect(0, 336, cw, 56)
        a_row = self._row_frame(buf, rect, "fs")
        on = bool(d and d.fullscreen)
        cb = pygame.Rect(22, rect.centery - 14, 28, 28)
        pygame.draw.rect(buf, (6, 14, 22), cb, border_radius=6)
        pygame.draw.rect(buf, GREEN if on else _lerp((70, 100, 116), CYAN, a_row), cb, width=2, border_radius=6)
        if on:
            draw_glow_circle(buf, cb.centerx, cb.centery, 28, GREEN, intensity=0.4, layers=3)
            pygame.draw.lines(buf, GREEN, False, [(cb.left + 6, cb.centery), (cb.left + 12, cb.bottom - 8), (cb.right - 6, cb.top + 7)], 4)
        self._reg(cb.inflate(8, 8), "check", "fs")
        self._label(buf, "TELA CHEIA", (66, rect.centery), 19)
        self._label(buf, "ATIVADA" if on else "DESATIVADA", (230, rect.centery), 15, GREEN if on else MUTED)
        self._label(buf, "F11 ALTERNA EM QUALQUER MOMENTO", (cw - 22, rect.centery), 13, DIM, anchor="midright")
        if d is None:
            self._label(buf, "(vídeo indisponível nesta execução)", (24, 410), 13, AMBER)

    # ------------------------------------------------------------ aba CONTROLES
    def _segments(self, buf, rid, x, y, w, h, options, active):
        seg_w = w / len(options)
        for i, (label, col) in enumerate(options):
            r = pygame.Rect(int(x + i * seg_w), y, int(seg_w) - 6, h)
            on = i == active
            pygame.draw.rect(buf, col if on else (14, 26, 36), r, border_radius=8)
            pygame.draw.rect(buf, col, r, width=2, border_radius=8)
            self._label(buf, label, r.center, 16, (10, 14, 22) if on else col, anchor="center")
            self._reg(r, "seg", (rid, i))

    def _draw_controls(self, buf):
        g = self.game
        inp, gp = g.input, g.input.gamepad
        cw = self._content_size[0]
        p, dev = self.c_player, self.c_device
        fam = DEVICE_FAMILY[dev]
        pc = S.hx(S.PLAYER_DEFS[p]["color"])
        slot = inp.bindings[p].gamepad_slot
        connected = slot is not None and gp.is_connected(slot)
        info = (f"{S.PLAYER_DEFS[p]['short']} · CONTROLE: PAD {slot + 1} — {gp.name(slot)} ({GP.FAMILY_NAMES[gp.family(slot)]})"
                if connected else f"{S.PLAYER_DEFS[p]['short']} · NENHUM CONTROLE ASSOCIADO — USANDO TECLADO")
        self._label(buf, info, (4, 8), 14, MUTED)

        y = 22
        rect = pygame.Rect(0, y, cw, 42)
        self._row_frame(buf, rect, "player")
        self._label(buf, "JOGADOR", (24, rect.centery), 19)
        opts = [(S.PLAYER_DEFS[i]["short"], S.hx(S.PLAYER_DEFS[i]["color"])) for i in range(S.MAX_PLAYERS)]
        self._segments(buf, "player", 230, rect.top + 4, cw - 250, 34, opts, p)

        y += 46
        rect = pygame.Rect(0, y, cw, 38)
        self._row_frame(buf, rect, "pad")
        self._label(buf, "CONTROLE", (24, rect.centery), 19)
        left, right = pygame.Rect(230, rect.centery - 15, 32, 30), pygame.Rect(cw - 52, rect.centery - 15, 32, 30)
        for r, d_ in ((left, -1), (right, 1)):
            pygame.draw.rect(buf, (19, 34, 46), r, border_radius=7)
            pygame.draw.rect(buf, CYAN, r, width=2, border_radius=7)
            cx, cy = r.center
            pts = [(cx + 4, cy - 7), (cx - 4, cy), (cx + 4, cy + 7)] if d_ < 0 else [(cx - 4, cy - 7), (cx + 4, cy), (cx - 4, cy + 7)]
            pygame.draw.polygon(buf, TEXT, pts)
            self._reg(r, "arrow", ("pad", d_))
        txt = f"PAD {slot + 1} · {gp.name(slot)[:30]}" if connected else "NENHUM (TECLADO)"
        self._label(buf, txt, ((left.right + right.left) // 2, rect.centery), 16, TEXT if connected else MUTED, anchor="center")

        y += 42
        rect = pygame.Rect(0, y, cw, 42)
        self._row_frame(buf, rect, "device")
        self._label(buf, "EDITAR", (24, rect.centery), 19)
        dopts = [(S.CONTROL_DEVICE_LABELS[d_], CYAN if d_ == "keyboard" else (GREEN if d_ == "xbox" else (110, 168, 255)))
                 for d_ in S.CONTROL_DEVICES]
        self._segments(buf, "device", 230, rect.top + 4, cw - 250, 34, dopts, S.CONTROL_DEVICES.index(dev))

        y += 46
        self._label(buf, "AÇÃO", (22, y + 8), 12, DIM)
        note = {"keyboard": "TECLADO — qualquer tecla, exceto ESC / F / F11",
                "xbox": "PERFIL XBOX — também usado por controles Switch e genéricos",
                "playstation": "PERFIL PLAYSTATION — DualShock 4 / DualSense"}[dev]
        self._label(buf, note, (cw - 6, y + 8), 12, DIM, anchor="midright")

        y += 20
        for action in S.CONTROL_ACTIONS:
            rid = "act:" + action
            rect = pygame.Rect(0, y, cw, 36)
            a = self._row_frame(buf, rect, rid)
            capturing = self.capture is not None and self.capture["action"] == action and self.capture["player"] == p and self.capture["device"] == dev
            if capturing:
                pygame.draw.rect(buf, AMBER, rect, width=2, border_radius=8)
            self._label(buf, S.CONTROL_LABELS[action], (24, rect.centery), 18)
            self._draw_binding(buf, rect, action, p, dev, fam, capturing, a)
            y += 39

        rect = pygame.Rect(0, y + 4, cw, 40)
        a = self._row_frame(buf, rect, "restore")
        btn = pygame.Rect(0, 0, 300, 32)
        btn.midleft = (230, rect.centery)
        pygame.draw.rect(buf, _lerp((40, 30, 18), (70, 48, 20), a), btn, border_radius=8)
        pygame.draw.rect(buf, AMBER, btn, width=2, border_radius=8)
        self._label(buf, "RESTAURAR PADRÕES", btn.center, 17, (255, 225, 180), anchor="center")
        self._reg(btn, "button", "restore")
        self._label(buf, f"{S.PLAYER_DEFS[p]['short']} · {S.CONTROL_DEVICE_LABELS[dev]}", (cw - 22, rect.centery), 14, pc, anchor="midright")

    def _draw_binding(self, buf, rect, action, p, dev, fam, capturing, a):
        inp = self.game.input
        right = rect.right - 22
        if dev == "keyboard":
            code = inp.binding_value(p, dev, action)
            label = "..." if capturing else self._value_text(dev, code)
            font = get_font(S.FONT_UI_NAME, 17, bold=True)
            w = max(64, font.size(label)[0] + 28)
            cap = pygame.Rect(0, 0, w, 30)
            cap.midright = (right, rect.centery)
            draw_keycap(buf, cap, label, accent=AMBER if capturing else _lerp((65, 101, 120), CYAN, a),
                        fill=(60, 42, 18) if capturing else (19, 34, 46))
            custom = inp.is_customized(p, dev, action)
        elif action in S.PAD_ACTIONS:
            name = inp.binding_value(p, dev, action)
            if capturing:
                cap = pygame.Rect(0, 0, 64, 30)
                cap.midright = (right, rect.centery)
                draw_keycap(buf, cap, "...", accent=AMBER, fill=(60, 42, 18))
                w = 64
            else:
                w = draw_pad_glyph(buf, (right - 18, rect.centery), name, fam, r=14)
            custom = inp.is_customized(p, dev, action)
        else:
            txt = get_font(S.FONT_UI_NAME, 14, bold=True).render("DIRECIONAL ◄ ► / ANALÓGICO ESQ.", True, DIM)
            buf.blit(txt, txt.get_rect(midright=(right - 22, rect.centery)))
            pygame.draw.rect(buf, DIM, (right - 14, rect.centery - 2, 12, 9), border_radius=2)
            pygame.draw.arc(buf, DIM, pygame.Rect(right - 12, rect.centery - 9, 8, 12), 0, math.pi, 2)
            return
        if custom and not capturing:
            tag = get_font(S.FONT_UI_NAME, 11, bold=True).render("PERSONALIZADO", True, AMBER)
            buf.blit(tag, tag.get_rect(midright=(rect.right - 190, rect.centery)))

    # ------------------------------------------------------------ overlays: captura e confirmação
    def _card(self, surf, w, h):
        veil = self._dim
        veil.set_alpha(150)
        surf.blit(veil, (0, 0))
        veil.set_alpha(255)
        card = pygame.Rect(0, 0, w, h)
        card.center = (S.WIDTH // 2, S.HEIGHT // 2)
        self.game._draw_sci_panel(surf, card, accent=AMBER, fill=(10, 20, 31), radius=14, border=3)
        return card

    def _draw_capture(self, surf):
        c = self.capture
        card = self._card(surf, 620, 250)
        self._mhit = []
        dev = c["device"]
        t = pygame.time.get_ticks() / 1000.0
        title = "PRESSIONE A NOVA TECLA" if dev == "keyboard" else "PRESSIONE O NOVO BOTÃO"
        img = get_font(S.FONT_TITLE_NAME, 36).render(title, True, _lerp(AMBER, (255, 235, 190), pulse(t, 6.0, 0.0, 1.0)))
        surf.blit(img, img.get_rect(center=(card.centerx, card.top + 52)))
        what = f"{S.CONTROL_LABELS[c['action']]}  ·  {S.PLAYER_DEFS[c['player']]['short']}  ·  {S.CONTROL_DEVICE_LABELS[dev]}"
        what_img = get_font(S.FONT_UI_NAME, 18, bold=True).render(what, True, TEXT)
        surf.blit(what_img, what_img.get_rect(center=(card.centerx, card.top + 100)))
        # barra de tempo restante
        bar = pygame.Rect(card.left + 60, card.top + 128, card.width - 120, 8)
        pygame.draw.rect(surf, (6, 14, 22), bar, border_radius=4)
        frac = clamp(c["t"] / S.CAPTURE_TIMEOUT, 0.0, 1.0)
        pygame.draw.rect(surf, AMBER if frac > 0.3 else RED, (bar.left, bar.top, int(bar.width * frac), bar.height), border_radius=4)
        if c["msg_t"] > 0 and c["msg"]:
            m = get_font(S.FONT_UI_NAME, 17, bold=True).render(c["msg"], True, RED)
            surf.blit(m, m.get_rect(center=(card.centerx, card.top + 164)))
        else:
            tip = get_font(S.FONT_UI_NAME, 14).render("Se o comando já estiver em uso, você poderá trocá-los.", True, MUTED)
            surf.blit(tip, tip.get_rect(center=(card.centerx, card.top + 164)))
        cancel = pygame.Rect(0, 0, 200, 38)
        cancel.midbottom = (card.centerx, card.bottom - 18)
        pygame.draw.rect(surf, (24, 40, 52), cancel, border_radius=8)
        pygame.draw.rect(surf, AMBER, cancel, width=2, border_radius=8)
        ci = get_font(S.FONT_UI_NAME, 16, bold=True).render("CANCELAR (ESC)", True, (255, 225, 180))
        surf.blit(ci, ci.get_rect(center=cancel.center))
        self._mhit.append((cancel, "cancel"))

    def _draw_modal(self, surf):
        md = self.modal
        card = self._card(surf, 640, 240)
        self._mhit = []
        img = get_font(S.FONT_TITLE_NAME, 32).render(md["title"], True, AMBER)
        surf.blit(img, img.get_rect(center=(card.centerx, card.top + 40)))
        font = get_font(S.FONT_UI_NAME, 16)
        for i, line in enumerate(md["lines"]):
            li = font.render(line, True, TEXT)
            surf.blit(li, li.get_rect(center=(card.centerx, card.top + 86 + i * 24)))
        n = len(md["buttons"])
        for i, (label, ident) in enumerate(md["buttons"]):
            r = pygame.Rect(0, 0, 220, 42)
            r.midbottom = (card.centerx + (i - (n - 1) / 2) * 250, card.bottom - 20)
            sel = i == md["sel"]
            col = AMBER if ident in ("restore",) else (GREEN if ident == "swap" else CYAN)
            pygame.draw.rect(surf, _lerp((14, 26, 36), (30, 52, 66), 1.0 if sel else 0.0), r, border_radius=8)
            pygame.draw.rect(surf, col if sel else (60, 86, 100), r, width=3 if sel else 1, border_radius=8)
            li = get_font(S.FONT_UI_NAME, 18, bold=True).render(label, True, col if sel else MUTED)
            surf.blit(li, li.get_rect(center=r.center))
            self._mhit.append((r, i))

