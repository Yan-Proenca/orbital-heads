"""
game.py — estado central do jogo: states (title/setup/playing/paused/
keybinds/gameover/mvp), o "step" de um quadro, ligação entre todos os
sistemas (ondas, colisões, efeitos, áudio, input) e os menus, navegáveis
por teclado, mouse E controle (Xbox/PlayStation/Switch/genérico).

Fluxo de estados:
    title -> setup (modo de jogo -> dificuldade -> nº de jogadores) -> playing
    playing <-> paused -> keybinds (config. de controles) -> volta a paused
    playing -> gameover -> mvp (estatísticas) -> setup ou title
Tanto "paused" quanto "title" têm a opção SAIR DO JOGO (encerra o processo).
"""
import math
import random

import pygame

import settings as S
from audio import AudioManager
from input_handler import InputManager, key_name_for_rebind, display_label
from player import Player
from projectile import Projectile
from pickup import Pickup
from effects import Effects
from wave import WaveManager
from collisions import CollisionManager
from utils import clamp, circle_hits_rect, mult_clamp, get_font
from menu_input import MenuInput
from background import CityBackground
import gamepad as GP

# ----------------------------------------------------------------- menu de pausa
PAUSE_ITEMS = ("resume", "restart", "music", "keybinds", "main_menu", "quit")
PAUSE_LABELS = {
    "resume": "RESUMIR",
    "restart": "REINICIAR PARTIDA",
    "music": "MÚSICA: {state}",
    "keybinds": "CONFIGURAR CONTROLES",
    "main_menu": "MENU INICIAL",
    "quit": "SAIR DO JOGO",
}
TITLE_ITEMS = ("start", "quit")
TITLE_LABELS = {"start": "INICIAR JOGO", "quit": "SAIR DO JOGO"}

REBIND_ACTIONS = ("left", "right", "jump", "dash", "fire")
REBIND_ACTION_LABELS = {"left": "MOVER ESQUERDA", "right": "MOVER DIREITA", "jump": "PULAR",
                         "dash": "DASH", "fire": "ATIRAR"}

# ----------------------------------------------------------------- menu de configuração de partida
SETUP_STEPS = ("mode", "difficulty", "players")
SETUP_TITLES = {"mode": "MODO DE JOGO", "difficulty": "DIFICULDADE", "players": "JOGADORES"}


class Game:
    def __init__(self, screen):
        self.screen = screen
        self.audio = AudioManager()
        self.audio.init_mixer()
        self.audio.load_all()
        self.input = InputManager()
        self.menu = MenuInput(self.input)
        self.city = CityBackground()

        self.players = []
        self.projectiles = []
        self.pickups = []
        self.fx = Effects()
        self.wave = WaveManager(self)

        # --- escolhas da tela de configuração de partida (item 5 do pedido)
        self.game_mode = S.DEFAULT_GAME_MODE
        self.difficulty = S.DEFAULT_DIFFICULTY
        self.player_count = S.DEFAULT_PLAYER_COUNT
        self.rounds_to_win = S.GAME_MODES[self.game_mode]["rounds_to_win"]

        self.setup_step_i = 0
        self.setup_sel = dict(mode=S.GAME_MODE_ORDER.index(S.DEFAULT_GAME_MODE),
                               difficulty=S.DIFFICULTY_ORDER.index(S.DEFAULT_DIFFICULTY),
                               players=S.DEFAULT_PLAYER_COUNT - S.MIN_PLAYERS)

        self.global_effects = {}
        self.enemy_move_mult = self.enemy_proj_mult = self.enemy_attack_rate = 1.0

        self.state = "title"
        self.title_sel = 0
        self.pause_sel = 0
        self.rebinding = None          # (player_idx, action_index) quando aguardando nova tecla/botão
        self.keybinds_player = 0       # aba selecionada na tela de configuração de controles
        self.just = set()
        self.rounds_completed = 0
        self.drops_this_round = 0
        self.drop_cd = 0.0
        self.breach_cd = 0.0
        self.title_t = 0.0
        self.gameover_t = 0.0
        self.victory = False
        self.winner = None
        self.mvp = None
        self.running = True
        self.quit_requested = False

        self.flash_t = self.flash_dur = 0.0
        self.flash_color = (255, 0, 0)
        self.shake_t = self.shake_dur = 0.0
        self.shake_mag = 0.0
        self.shake_off = (0, 0)
        self.banner = None
        self.perf_level = 0
        self._fps_ema = S.FPS

        self.audio.play_music("title")

    @property
    def diff(self):
        return S.DIFFICULTIES[self.difficulty]

    # ------------------------------------------------------------ transições de estado
    def start_match(self):
        n = self.player_count
        self.players = [Player(self, i, S.PLAYER_DEFS[i]) for i in range(n)]
        self.projectiles.clear()
        self.pickups.clear()
        self.global_effects.clear()
        self.fx.clear()
        self.wave.reset()
        self.rounds_to_win = S.GAME_MODES[self.game_mode]["rounds_to_win"]
        self.rounds_completed = 0
        self.drop_cd = 0.0
        self.breach_cd = 0.0
        self.victory = False
        self.winner = None
        self.mvp = None
        self.banner = None
        self.state = "playing"
        self.wave.begin_round(1)
        self.audio.play_music("gameplay")
        self._apply_gamepad_leds()

    def restart_match(self):
        self.start_match()

    def go_to_title(self):
        self.state = "title"
        self.title_sel = 0
        self.title_t = 0.0
        self.menu.reset_hover()
        self.audio.play_music("title")

    def enter_setup(self):
        """Abre o fluxo de configuração de partida: modo -> dificuldade -> jogadores."""
        self.state = "setup"
        self.setup_step_i = 0
        self.menu.reset_hover()

    def toggle_pause(self):
        if self.state == "playing":
            self.state = "paused"
            self.pause_sel = 0
            self.menu.reset_hover()
        elif self.state == "paused":
            self.state = "playing"

    def request_quit(self):
        """SAIR DO JOGO: sinaliza para main.py encerrar o loop principal."""
        self.running = False

    def _apply_gamepad_leds(self):
        """Acende a luz (PS4/PS5) de cada controle em uso com a cor do jogador
        correspondente — puramente estético, e seguro mesmo sem controle com LED."""
        gp = self.input.gamepad
        for i, p in enumerate(self.players):
            b = self.input.bindings[i] if i < len(self.input.bindings) else None
            if b is not None and b.gamepad_slot is not None and gp.is_connected(b.gamepad_slot):
                color = S.GAMEPAD_LED_COLORS[i % len(S.GAMEPAD_LED_COLORS)]
                gp.set_led(b.gamepad_slot, color)

    # ------------------------------------------------------------ um quadro
    def step(self, dt):
        self.just = self.input.take_pressed()
        self.menu.update(dt)
        self.city.update(dt)

        if self.state == "title":
            self.title_t += dt
            self._update_title_menu()
        elif self.state == "setup":
            self._update_setup_menu()
        elif self.state == "playing":
            self._handle_playing_globals()
            if self.state == "playing":
                self.update(dt)
        elif self.state == "paused":
            self._update_pause_menu()
        elif self.state == "keybinds":
            self._update_keybinds_menu()
        elif self.state == "gameover":
            self.gameover_t += dt
            if self.gameover_t > S.GAMEOVER_INPUT_LOCK and self._confirm_pressed():
                self._enter_mvp_screen()
        elif self.state == "mvp":
            self._update_mvp_screen()

    def _confirm_pressed(self):
        return ("global_return" in self.just or "global_space" in self.just
                or self.menu.confirm_clicked or "global_gp_confirm" in self.just)

    def _back_pressed(self):
        return "global_escape" in self.just or self.menu.back_clicked or "global_gp_back" in self.just

    def _handle_playing_globals(self):
        if "global_escape" in self.just:
            self.toggle_pause()
        elif "global_f11" in self.just or "global_f" in self.just:
            try:
                pygame.display.toggle_fullscreen()
            except pygame.error:
                pass

    # ------------------------------------------------------------ menu de título (item 3: SAIR DO JOGO aqui também)
    def _update_title_menu(self):
        nav = self.menu.nav_delta()
        if nav:
            self.title_sel = (self.title_sel + nav) % len(TITLE_ITEMS)
            self.audio.on_menu_move()
        if self.menu.hovered_index is not None and self.menu.hovered_index != self.title_sel:
            self.title_sel = self.menu.hovered_index
        if self._confirm_pressed():
            self.audio.on_menu_confirm()
            item = TITLE_ITEMS[self.title_sel]
            if item == "start":
                self.enter_setup()
            elif item == "quit":
                self.request_quit()

    # ------------------------------------------------------------ fluxo de configuração de partida (item 5)
    def _setup_options(self, step):
        if step == "mode":
            return [S.GAME_MODES[k]["label"] for k in S.GAME_MODE_ORDER]
        if step == "difficulty":
            return [S.DIFFICULTIES[k]["label"] for k in S.DIFFICULTY_ORDER]
        return [str(n) for n in range(S.MIN_PLAYERS, S.MAX_PLAYERS + 1)]

    def _setup_desc(self, step):
        if step == "mode":
            key = S.GAME_MODE_ORDER[self.setup_sel["mode"]]
            return S.GAME_MODES[key]["desc"]
        if step == "difficulty":
            key = S.DIFFICULTY_ORDER[self.setup_sel["difficulty"]]
            return S.DIFFICULTIES[key]["desc"]
        n = S.MIN_PLAYERS + self.setup_sel["players"]
        connected = sum(1 for i in range(min(n, len(self.input.bindings)))
                         if self.input.player_uses_gamepad(i))
        return f"{n} jogador{'es' if n != 1 else ''} no mesmo jogo — {connected} com controle, {n - connected} no teclado."

    def _update_setup_menu(self):
        step = SETUP_STEPS[self.setup_step_i]
        options = self._setup_options(step)
        nav = self.menu.nav_delta()
        if nav:
            self.setup_sel[step] = (self.setup_sel[step] + nav) % len(options)
            self.audio.on_menu_move()
        if self.menu.hovered_index is not None and self.menu.hovered_index != self.setup_sel[step]:
            self.setup_sel[step] = self.menu.hovered_index

        if self._confirm_pressed():
            self.audio.on_menu_confirm()
            if self.setup_step_i < len(SETUP_STEPS) - 1:
                self.setup_step_i += 1
                self.menu.reset_hover()
            else:
                self.game_mode = S.GAME_MODE_ORDER[self.setup_sel["mode"]]
                self.difficulty = S.DIFFICULTY_ORDER[self.setup_sel["difficulty"]]
                self.player_count = S.MIN_PLAYERS + self.setup_sel["players"]
                self.start_match()
        elif self._back_pressed():
            if self.setup_step_i > 0:
                self.setup_step_i -= 1
                self.menu.reset_hover()
            else:
                self.go_to_title()

    # ------------------------------------------------------------ menu de pausa/configurações
    def _update_pause_menu(self):
        nav = self.menu.nav_delta()
        if nav:
            self.pause_sel = (self.pause_sel + nav) % len(PAUSE_ITEMS)
            self.audio.on_menu_move()
        if self.menu.hovered_index is not None and self.menu.hovered_index != self.pause_sel:
            self.pause_sel = self.menu.hovered_index
        if self._back_pressed():
            self.state = "playing"
        elif self._confirm_pressed():
            self._activate_pause_item(PAUSE_ITEMS[self.pause_sel])

    def _activate_pause_item(self, item):
        self.audio.on_menu_confirm()
        if item == "resume":
            self.state = "playing"
        elif item == "restart":
            self.restart_match()
        elif item == "music":
            self.audio.toggle_music()
        elif item == "keybinds":
            self._enter_keybinds_screen(return_to="paused")
        elif item == "main_menu":
            self.go_to_title()
        elif item == "quit":
            self.request_quit()

    def pause_label(self, item):
        if item == "music":
            return PAUSE_LABELS[item].format(state="LIGADA" if self.audio.music_enabled else "DESLIGADA")
        return PAUSE_LABELS[item]

    # ------------------------------------------------------------ tela de configuração de controles (item 4)
    def _enter_keybinds_screen(self, return_to="paused"):
        self._keybinds_return_to = return_to
        self.state = "keybinds"
        self.keybinds_player = 0
        self.rebinding = None
        self.menu.reset_hover()

    def _keybinds_action_count(self):
        return len(REBIND_ACTIONS)

    def _update_keybinds_menu(self):
        if self.rebinding is not None:
            self._update_rebind_capture()
            return

        n_players = max(1, len(self.players) or self.player_count)
        # --- trocar de aba de jogador: ←/→, ou clicar nas abas (áreas extras registradas no draw)
        if "global_left" in self.just:
            self.keybinds_player = (self.keybinds_player - 1) % n_players
            self.audio.on_menu_move()
        elif "global_right" in self.just:
            self.keybinds_player = (self.keybinds_player + 1) % n_players
            self.audio.on_menu_move()

        nav = self.menu.nav_delta()
        actions_n = self._keybinds_action_count()
        total_rows = actions_n + 2   # + "Restaurar Padrões" + "Voltar"
        if not hasattr(self, "_keybinds_row"):
            self._keybinds_row = 0
        if nav:
            self._keybinds_row = (self._keybinds_row + nav) % total_rows
            self.audio.on_menu_move()
        if self.menu.hovered_index is not None:
            if self.menu.hovered_index < 0:   # abas de jogador usam índices negativos (ver draw)
                tab = -self.menu.hovered_index - 1
                if tab != self.keybinds_player:
                    self.keybinds_player = tab
                    self.audio.on_menu_move()
            elif self.menu.hovered_index != self._keybinds_row:
                self._keybinds_row = self.menu.hovered_index

        if self._back_pressed():
            self.audio.on_menu_confirm()
            self.state = self._keybinds_return_to
            self.menu.reset_hover()
            return

        if self._confirm_pressed():
            self.audio.on_menu_confirm()
            if self._keybinds_row < actions_n:
                self._start_rebind_capture(self.keybinds_player, self._keybinds_row)
            elif self._keybinds_row == actions_n:
                self._reset_player_defaults(self.keybinds_player)
            else:
                self.state = self._keybinds_return_to
                self.menu.reset_hover()

    def _reset_player_defaults(self, player_idx):
        defaults = S.PLAYER_DEFS[player_idx]["key_names"]
        for action, key_name in defaults.items():
            try:
                self.input.rebind_key(player_idx, action, key_name)
            except ValueError:
                pass
        self.audio.on_menu_confirm()

    def _start_rebind_capture(self, player_idx, act_idx):
        self.rebinding = (player_idx, act_idx)
        self.input.text_input_active = True
        self.input.last_key_pressed = None
        self.input.last_gamepad_button = None

    def _update_rebind_capture(self):
        """Tela 'pressione uma tecla OU um botão' para UMA ação; aceita teclado
        e controle, o que vier primeiro. ESC/B cancela sem alterar nada."""
        if self._back_pressed():
            self.rebinding = None
            self.input.text_input_active = False
            return
        p_idx, act_idx = self.rebinding
        action = REBIND_ACTIONS[act_idx]
        key = self.input.last_key_pressed
        gp_hit = self.input.last_gamepad_button
        if key is not None:
            name = key_name_for_rebind(key)
            alias = {"left shift": "shift"}.get(name, name)
            try:
                self.input.rebind_key(p_idx, action, alias)
                self.audio.on_menu_confirm()
            except ValueError:
                pass
            self.input.last_key_pressed = None
            self.rebinding = None
            self.input.text_input_active = False
        elif gp_hit is not None:
            slot, button_name = gp_hit
            # mapear controle por ação-por-jogador exigiria um esquema de botões
            # por jogador (hoje settings.GAMEPAD_BUTTONS é global); por ora,
            # apertar um botão do controle durante a captura associa aquele
            # controle inteiro a este jogador (o padrão esperado: "jogador 2,
            # aperte qualquer botão no SEU controle para usá-lo").
            self.input.assign_gamepad(p_idx, slot)
            self.audio.on_menu_confirm()
            self.input.last_gamepad_button = None
            self.rebinding = None
            self.input.text_input_active = False

    # ------------------------------------------------------------ tela de MVP / resumo (item 6)
    def _enter_mvp_screen(self):
        self.mvp = self._determine_mvp()
        self.state = "mvp"
        self.menu.reset_hover()

    def _determine_mvp(self):
        """MVP = maior pontuação; empate de pontuação é resolvido por mais abates."""
        if not self.players:
            return None
        return max(self.players, key=lambda p: (p.score, p.kills))

    def _update_mvp_screen(self):
        nav = self.menu.nav_delta()  # não há navegação vertical aqui, mas consome eventuais toques sem efeito
        if self._confirm_pressed() or "global_r" in self.just:
            self.restart_match()
        elif self._back_pressed() or "global_m" in self.just:
            self.enter_setup()
        elif "global_q" in self.just:
            self.go_to_title()

    # ------------------------------------------------------------ gameplay
    def update(self, dt):
        self._track_perf(dt)
        self._update_global_effects(dt)
        self.wave.update(dt)
        for p in self.players:
            p.update(dt)
        mult = self.enemy_proj_mult
        for b in list(self.projectiles):
            b.update(dt, mult if b.owner is None else 1.0)
            self._projectile_bounds(b)
        for pk in list(self.pickups):
            pk.update(dt)
        self.drop_cd = max(0.0, self.drop_cd - dt)
        self.breach_cd = max(0.0, self.breach_cd - dt)
        self.collisions.update()
        self._cleanup()
        load = len(self.wave.enemies) + 0.5 * len(self.projectiles)
        self.fx.set_load(load, self.perf_level)
        self.fx.update(dt)
        if self.banner is not None:
            self.banner["t"] -= dt
            if self.banner["t"] <= 0:
                self.banner = None
        if self.players and all(p.eliminated for p in self.players):
            self.end_match(False)

    def _track_perf(self, dt):
        fps = 1.0 / dt if dt > 0 else S.FPS
        self._fps_ema += (fps - self._fps_ema) * S.PERF_EMA
        if self._fps_ema < S.FPS_LOD_LOW:
            self.perf_level = 2
        elif self._fps_ema < S.FPS_LOD_MEDIUM:
            self.perf_level = 1
        else:
            self.perf_level = 0

    def _update_global_effects(self, dt):
        ge = self.global_effects
        if not ge:
            self.enemy_move_mult = self.enemy_proj_mult = self.enemy_attack_rate = 1.0
            return
        for k in list(ge):
            ge[k] -= dt
            if ge[k] <= 0:
                del ge[k]
        self.enemy_move_mult = mult_clamp([S.BOOSTS[k]["enemy_move"] for k in ge], S.ENEMY_MULT_LIMITS)
        self.enemy_proj_mult = mult_clamp([S.BOOSTS[k]["enemy_proj"] for k in ge], S.ENEMY_MULT_LIMITS)
        self.enemy_attack_rate = mult_clamp([S.BOOSTS[k]["enemy_attack"] for k in ge], S.ENEMY_MULT_LIMITS)

    def _projectile_bounds(self, b):
        """Remove tiros fora da área, detona orbes cujo pavio acabou e bombas que tocam o chão."""
        if b.owner is not None:
            if b.y + b.h / 2 < S.HUD_H or b.x < -40 or b.x > S.WIDTH + 40:
                b.alive = False
            return
        if b.fuse is not None and b.fuse <= 0:
            self.detonate(b, "fuse")
        elif b.y + b.h / 2 >= S.GROUND_Y:
            if b.blast:
                self.detonate(b, "ground")
            else:
                b.alive = False
                self.fx.impact(b.x, S.GROUND_Y, S.hx("#ff7a1a"))
        elif b.x < -60 or b.x > S.WIDTH + 60 or b.y < -80:
            b.alive = False

    def _cleanup(self):
        self.projectiles = [b for b in self.projectiles if b.alive]
        self.pickups = [pk for pk in self.pickups if pk.alive]

    # ------------------------------------------------------------ armas / tiro
    def count_shots(self, p):
        return sum(1 for b in self.projectiles if b.owner is p and b.alive)

    def fire_weapon(self, p, wp):
        n, spread = wp["count"], math.radians(wp["spread"])
        for i in range(n):
            ang = 0.0 if n == 1 else -spread / 2 + spread * i / (n - 1)
            b = Projectile(p, p.x, p.y - 72, -wp["speed"] * math.cos(ang), vx=wp["speed"] * math.sin(ang),
                            damage=wp["damage"], style=wp["style"], w=wp["w"], h=wp["h"], color=wp["color"],
                            max_range=wp["range"])
            self.projectiles.append(b)
        if self.fx.level < 2:
            if p.weapon == "machinegun":
                self.fx.casing(p.x + 7, p.y - 60, 1 if p.facing > 0 else -1)
            elif p.weapon == "shotgun":
                self.fx.sparks(p.x, p.y - 76, wp["color"], 5)
            elif p.weapon == "rifle":
                self.fx.ring(p.x, p.y - 76, 4, 24, wp["color"], 0.18, 2)
        self.audio.on_shoot(p.weapon)

    def spawn_player_shot(self, player, weapon):
        self.fire_weapon(player, weapon)

    # ------------------------------------------------------------ ataques inimigos / explosões
    def alive_players(self):
        return [p for p in self.players if p.active]

    def random_target(self):
        al = self.alive_players()
        return random.choice(al) if al else None

    def spawn_hostile(self, kind, x, y, vx=0.0, vy=0.0, **kw):
        if sum(1 for b in self.projectiles if b.owner is None) >= S.MAX_HOSTILE_PROJECTILES:
            return None
        ps = self.diff["proj_speed"]
        sp = kw.get("spiral")
        if sp:
            sp["gvx"] *= ps
            sp["gvy"] *= ps
        b = Projectile(None, x, y, vy * ps, vx=vx * ps, kind=kind, **kw)
        self.projectiles.append(b)
        return b

    def polar_bullet(self, x, y, angle, speed):
        return self.spawn_hostile("bullet", x, y, vx=speed * math.sin(angle), vy=speed * math.cos(angle))

    def aim_bullet(self, x, y, target, speed, off=0.0):
        return self.polar_bullet(x, y, math.atan2(target.x - x, target.y - 30 - y) + off, speed)

    def area_blast(self, x, y, radius):
        self.fx.blast(x, y, radius)
        self.shake(0.18, 4)
        for p in self.players:
            if p.can_be_hit() and circle_hits_rect(x, y, radius, p.hitbox()):
                p.take_hit()

    def detonate(self, b, mode):
        if b.exploded:
            return
        b.exploded = True
        b.alive = False
        self.audio.on_explosion(big=bool(b.blast and b.blast > 70))
        if mode == "air":
            self.area_blast(b.x, min(b.y, S.GROUND_Y - 4), b.air_blast or b.blast)
        else:
            self.area_blast(b.x, S.GROUND_Y - 6 if mode == "ground" else min(b.y, S.GROUND_Y - 4), b.blast)

    def on_stomp(self, car, p):
        if car.stomp(p):
            self.on_enemy_destroyed(car, p)

    # ------------------------------------------------------------ eventos de jogo
    def on_player_eliminated(self, p):
        if self.players and all(q.eliminated for q in self.players):
            self.end_match(False)

    def on_round_cleared(self, n):
        self.rounds_completed += 1
        self.show_banner("ROUND %d CONCLUÍDO!" % n, "Preparar próxima onda...", "#46f08a", S.ROUND_CLEAR_TIME)
        self.audio.on_round_clear()

    def on_enemy_destroyed(self, e, killer):
        if killer is not None:
            killer.score += e.points
            killer.kills += 1
            killer.kills_by_type[e.kind] = killer.kills_by_type.get(e.kind, 0) + 1
            self.fx.popup(e.x, e.y - e.h / 2, "+%d" % e.points, killer.cfg["color"], 30 if e.is_boss else 22)
        self.fx.explosion(e.x, e.y, e.cfg["size"], *e.cfg["fx"], priority=e.is_boss)
        self.audio.on_explosion(big=e.is_boss or e.kind == "machine")
        if e.kind == "machine":
            self.shake(0.25, 5)
        e.on_destroyed(self)
        self.roll_drop(e.kind, e.x, e.y)
        self.wave.remove_enemy(e)

    def on_projectile_destroyed(self, b, killer):
        if b.exploded:
            return
        if killer is not None:
            pts = S.ENEMY_TYPES["jetbomb"]["points"]
            killer.score += pts
            killer.kills += 1
            killer.kills_by_type["jetbomb"] = killer.kills_by_type.get("jetbomb", 0) + 1
            self.fx.popup(b.x, b.y - 20, "+%d" % pts, killer.cfg["color"], 18)
        self.roll_drop("jetbomb", b.x, b.y)
        self.detonate(b, "air")

    # ------------------------------------------------------------ boosts, drops, pickups
    def roll_drop(self, kind, x, y):
        if self.state != "playing":
            return None
        mult = S.DROP_SOURCE_MULT.get(kind, 0.0)
        if (mult <= 0 or self.drop_cd > 0 or self.drops_this_round >= S.MAX_DROPS_PER_ROUND
                or len(self.pickups) >= S.MAX_PICKUPS):
            return None
        d = self.diff
        item = None
        if random.random() < min(1.0, d["drop_chance"] * mult):
            good = random.random() < d["good_ratio"]
            item = ("boost", random.choice(S.GOOD_BOOSTS if good else S.BAD_BOOSTS))
        elif random.random() < min(1.0, S.WEAPON_DROP_CHANCE * mult):
            item = ("weapon", random.choices(S.WEAPON_ORDER, weights=[S.WEAPONS[k]["weight"] for k in S.WEAPON_ORDER])[0])
        if item is None:
            return None
        return self.spawn_pickup(item[0], item[1], x, y)

    def spawn_pickup(self, kind, key, x, y):
        pk = Pickup(kind, key, clamp(x, 30, S.WIDTH - 30), clamp(y, S.HUD_H + 20, S.GROUND_Y - 60))
        self.pickups.append(pk)
        self.drops_this_round += 1
        self.drop_cd = S.DROP_COOLDOWN
        return pk

    def collect(self, p, pk):
        if pk.collected or not pk.alive:
            return
        pk.collected = True
        pk.alive = False
        if pk.kind == "weapon":
            p.set_weapon(pk.key)
            col, text = S.WEAPONS[pk.key]["color"] or "#ffffff", S.WEAPONS[pk.key]["name"]
            self.audio.on_pickup("weapon")
        else:
            b = S.BOOSTS[pk.key]
            if b["scope"] == "player":
                p.add_effect(pk.key)
            else:
                self.global_effects[pk.key] = b["duration"]
            col, text = b["color"], b["name"]
            self.audio.on_pickup("boost", good=b["good"])
        self.fx.ring(p.x, p.y - 30, 10, 54, col, 0.4)
        self.fx.popup(p.x, p.y - 90, text, col, 18)

    def determine_winner(self):
        """Vencedor por pontuação, desempatado por vidas restantes — funciona para 1 a 4 jogadores."""
        if not self.players:
            return None
        if len(self.players) == 1:
            return self.players[0] if not self.players[0].eliminated else None
        ranked = sorted(self.players, key=lambda p: (p.score, p.lives), reverse=True)
        if len(ranked) > 1 and ranked[0].score == ranked[1].score and ranked[0].lives == ranked[1].lives:
            return None    # empate exato no topo
        return ranked[0]

    def end_match(self, victory):
        if self.state == "gameover":
            return
        self.state = "gameover"
        self.victory = victory
        self.winner = self.determine_winner()
        self.gameover_t = 0.0
        self.banner = None
        if victory:
            self.audio.on_victory()
            self.audio.play_music("victory")
        else:
            self.audio.on_gameover()

    # ------------------------------------------------------------ efeitos de tela
    def flash(self, color, dur):
        self.flash_t = self.flash_dur = dur
        self.flash_color = S.hx(color)

    def shake(self, dur, mag):
        self.shake_t = self.shake_dur = dur
        self.shake_mag = mag

    def _apply_shake(self, dt):
        if self.shake_t > 0:
            self.shake_t -= dt
            k = max(0.0, self.shake_t / max(self.shake_dur, 1e-6))
            ix = int(random.uniform(-1, 1) * self.shake_mag * k)
            iy = int(random.uniform(-1, 1) * self.shake_mag * k)
        else:
            ix = iy = 0
        self.shake_off = (ix, iy)

    def show_banner(self, title, sub, color, duration, alert=False):
        self.banner = dict(title=title, sub=sub, color=color, t=duration, alert=alert)

    # ------------------------------------------------------------ desenho
    def draw(self, surf):
        surf.fill((8, 10, 24))
        if self.state == "title":
            self._draw_title(surf)
            return
        if self.state == "setup":
            self._draw_setup(surf)
            return

        self._apply_shake(1 / S.FPS)
        world = surf
        ox, oy = self.shake_off
        if ox or oy:
            world = pygame.Surface((S.WIDTH, S.HEIGHT))
            world.fill((8, 10, 24))
            self._draw_world(world)
            surf.blit(world, (ox, oy))
        else:
            self._draw_world(surf)

        if self.flash_t > 0:
            self.flash_t -= 1 / S.FPS
            a = int(90 * clamp(self.flash_t / max(self.flash_dur, 1e-6), 0.0, 1.0))
            flash_surf = pygame.Surface((S.WIDTH, S.HEIGHT), pygame.SRCALPHA)
            flash_surf.fill((*self.flash_color, a))
            surf.blit(flash_surf, (0, 0))

        if self.banner is not None:
            self._draw_banner(surf)

        if self.state == "paused":
            self._draw_pause_overlay(surf)
        elif self.state == "keybinds":
            self._draw_keybinds_screen(surf)
        elif self.state == "gameover":
            self._draw_gameover(surf)
        elif self.state == "mvp":
            self._draw_mvp_screen(surf)

    def _draw_world(self, surf):
        self._draw_background(surf)
        self.wave.draw(surf)
        for pk in self.pickups:
            pk.draw(surf, self._pickup_font())
        for b in self.projectiles:
            b.draw(surf)
        for p in self.players:
            p.draw(surf)
        self.fx.draw(surf)
        self._draw_hud(surf)

    def _pickup_font(self):
        return get_font(S.FONT_UI_NAME, 20, bold=True)

    def _draw_background(self, surf):
        self.city.draw(surf)

    def _draw_sci_panel(self, surf, rect, accent=(57, 190, 216), fill=(12, 22, 34), radius=10, border=2):
        """Painel metálico discreto usado pela interface tática."""
        pygame.draw.rect(surf, (3, 7, 13), rect.move(0, 3), border_radius=radius)
        pygame.draw.rect(surf, fill, rect, border_radius=radius)
        pygame.draw.rect(surf, (43, 61, 76), rect, width=1, border_radius=radius)
        pygame.draw.rect(surf, accent, (rect.left + 2, rect.top + 8, 3, max(12, rect.height - 16)), border_radius=2)
        # Pequenos recortes nos cantos dão leitura de chapa industrial.
        pygame.draw.line(surf, accent, (rect.left + 12, rect.top + 2), (rect.left + 42, rect.top + 2), border)
        pygame.draw.line(surf, accent, (rect.right - 42, rect.bottom - 2), (rect.right - 12, rect.bottom - 2), border)

    def _draw_hud(self, surf):
        font = get_font(S.FONT_UI_NAME, 18, bold=True)
        small = get_font(S.FONT_UI_NAME, 13)
        # Faixa de comando em grafite, com linha de status ciano.
        pygame.draw.rect(surf, (5, 10, 17), (0, 0, S.WIDTH, S.HUD_H))
        pygame.draw.line(surf, (38, 95, 117), (0, S.HUD_H - 2), (S.WIDTH, S.HUD_H - 2), 2)
        pygame.draw.line(surf, (61, 190, 211), (0, S.HUD_H - 2), (max(80, S.WIDTH // 5), S.HUD_H - 2), 2)

        n = len(self.players)
        if n <= 2:
            slots = [(12, False), (S.WIDTH - 272, False)][:n]
            block_w = min(250, S.WIDTH // 3)
        else:
            block_w = (S.WIDTH - 32) // n
            slots = [(16 + i * block_w, True) for i in range(n)]

        for i, p in enumerate(self.players):
            x0, compact = slots[i] if i < len(slots) else (16, True)
            panel_w = block_w if n > 2 else min(250, S.WIDTH // 3)
            panel = pygame.Rect(x0, 5, max(120, panel_w - 10), S.HUD_H - 12)
            self._draw_sci_panel(surf, panel, accent=p.color, fill=(10, 19, 29), radius=7, border=2)
            title = font.render(p.name if not compact else p.short, True, p.color)
            surf.blit(title, (panel.left + 13, panel.top + 4))
            weapon_label = S.WEAPONS[p.weapon]['name'] if not compact else S.WEAPONS[p.weapon]['name'][:3]
            stat = small.render(f"VIDAS {p.lives}   PTS {p.score}   {weapon_label.upper()}", True, (194, 211, 222))
            surf.blit(stat, (panel.left + 13, panel.top + 27))
            eff_x, eff_y = panel.left + 13, panel.top + 44
            for key, remaining in p.effects.items():
                b = S.BOOSTS[key]
                chip = small.render(f"{b['chip']} {remaining:0.1f}s", True, S.hx(b["color"]))
                surf.blit(chip, (eff_x, eff_y))
                eff_x += chip.get_width() + 12
                if eff_x > panel.right - 75:
                    eff_x, eff_y = panel.left + 13, eff_y + 13

        # Indicador central do round, em formato de módulo de telemetria.
        round_rect = pygame.Rect(S.WIDTH // 2 - 88, 8, 176, max(42, S.HUD_H - 18))
        self._draw_sci_panel(surf, round_rect, accent=(255, 176, 74), fill=(15, 24, 34), radius=7, border=1)
        round_txt = font.render(f"ROUND {self.wave.round_no:02d}/{self.rounds_to_win:02d}", True, (255, 190, 94))
        surf.blit(round_txt, round_txt.get_rect(center=(round_rect.centerx, round_rect.centery)))

        if self.global_effects:
            gx = round_rect.centerx
            gy = round_rect.bottom + 2
            for key, remaining in self.global_effects.items():
                b = S.BOOSTS[key]
                chip = small.render(f"{b['chip']} {remaining:0.1f}s", True, S.hx(b["color"]))
                surf.blit(chip, chip.get_rect(midtop=(gx, gy)))
                gy += 13

    def _draw_banner(self, surf):
        b = self.banner
        font_title = get_font(S.FONT_TITLE_NAME, 40)
        font_sub = get_font(S.FONT_UI_NAME, 20)
        if b.get("alert") and int(b["t"] * 4) % 2 == 0:
            overlay = pygame.Surface((S.WIDTH, 120), pygame.SRCALPHA)
            overlay.fill((*S.hx(b["color"]), 40))
            surf.blit(overlay, (0, S.HEIGHT // 2 - 60))
        title = font_title.render(b["title"], True, S.hx(b["color"]) if isinstance(b["color"], str) else b["color"])
        surf.blit(title, title.get_rect(center=(S.WIDTH // 2, S.HEIGHT // 2 - 20)))
        sub = font_sub.render(b["sub"], True, (230, 230, 240))
        surf.blit(sub, sub.get_rect(center=(S.WIDTH // 2, S.HEIGHT // 2 + 24)))

    def _draw_title(self, surf):
        self.city.draw(surf)
        overlay = pygame.Surface((S.WIDTH, S.HEIGHT), pygame.SRCALPHA)
        overlay.fill((3, 8, 15, 168))
        surf.blit(overlay, (0, 0))

        # Moldura de interface inspirada em console militar futurista.
        panel = pygame.Rect(0, 0, min(620, S.WIDTH - 48), 390)
        panel.center = (S.WIDTH // 2, S.HEIGHT // 2 + 12)
        self._draw_sci_panel(surf, panel, accent=(55, 197, 220), fill=(8, 18, 29), radius=14, border=3)
        micro = get_font(S.FONT_UI_NAME, 13, bold=True).render("SISTEMA DE COMBATE // TERMINAL 07", True, (107, 153, 172))
        surf.blit(micro, micro.get_rect(midtop=(panel.centerx, panel.top + 22)))
        font_title = get_font(S.FONT_TITLE_NAME, 64)
        title = font_title.render("ORBITAL HEADS", True, (224, 239, 246))
        accent_title = font_title.render("ORBITAL HEADS", True, (45, 156, 184))
        surf.blit(accent_title, accent_title.get_rect(center=(S.WIDTH // 2 + 2, panel.top + 100)))
        surf.blit(title, title.get_rect(center=(S.WIDTH // 2, panel.top + 97)))
        pygame.draw.line(surf, (45, 116, 137), (panel.left + 70, panel.top + 140), (panel.right - 70, panel.top + 140), 1)
        sub = get_font(S.FONT_UI_NAME, 15).render("PROTOCOLO DE DEFESA  /  UNIDADES HOSTIS DETECTADAS", True, (139, 172, 188))
        surf.blit(sub, sub.get_rect(center=(panel.centerx, panel.top + 162)))

        font = get_font(S.FONT_UI_NAME, 23, bold=True)
        areas = []
        for i, item in enumerate(TITLE_ITEMS):
            selected = i == self.title_sel
            rect = pygame.Rect(0, 0, 290, 46)
            rect.center = (panel.centerx, panel.top + 232 + i * 58)
            accent = (255, 176, 74) if item == "quit" else (55, 197, 220)
            fill = (25, 42, 53) if selected else (12, 25, 36)
            pygame.draw.rect(surf, fill, rect, border_radius=6)
            pygame.draw.rect(surf, accent if selected else (48, 72, 86), rect, width=2 if selected else 1, border_radius=6)
            if selected:
                pygame.draw.rect(surf, accent, (rect.left + 8, rect.top + 8, 4, rect.height - 16), border_radius=2)
            txt = font.render(TITLE_LABELS[item], True, accent if selected else (183, 201, 212))
            surf.blit(txt, txt.get_rect(center=rect.center))
            areas.append(rect.inflate(8, 4))
        self.menu.register_hit_areas(areas)
        hint = get_font(S.FONT_UI_NAME, 14).render("ENTER / ESPAÇO / CLIQUE / A NO CONTROLE", True, (115, 148, 165))
        surf.blit(hint, hint.get_rect(center=(panel.centerx, panel.bottom - 18)))
        self.menu.draw_cursor(surf)

    def _draw_setup(self, surf):
        self.city.draw(surf)
        overlay = pygame.Surface((S.WIDTH, S.HEIGHT), pygame.SRCALPHA)
        overlay.fill((3, 8, 15, 185))
        surf.blit(overlay, (0, 0))
        panel = pygame.Rect(0, 0, min(720, S.WIDTH - 48), min(650, S.HEIGHT - 70))
        panel.center = (S.WIDTH // 2, S.HEIGHT // 2)
        self._draw_sci_panel(surf, panel, accent=(55, 197, 220), fill=(8, 18, 29), radius=12, border=2)

        step = SETUP_STEPS[self.setup_step_i]
        font_title = get_font(S.FONT_TITLE_NAME, 36)
        title = font_title.render(SETUP_TITLES[step], True, (225, 239, 245))
        surf.blit(title, title.get_rect(center=(panel.centerx, panel.top + 48)))
        step_font = get_font(S.FONT_UI_NAME, 13, bold=True)
        for i, st in enumerate(SETUP_STEPS):
            done, current = i < self.setup_step_i, i == self.setup_step_i
            col = (91, 220, 177) if done else ((255, 176, 74) if current else (83, 107, 122))
            cx = panel.centerx - 150 + i * 150
            pygame.draw.circle(surf, col, (cx, panel.top + 94), 5 if current else 4)
            label = step_font.render(SETUP_TITLES[st], True, col)
            surf.blit(label, label.get_rect(center=(cx, panel.top + 112)))
            if i < len(SETUP_STEPS) - 1:
                pygame.draw.line(surf, (57, 82, 98), (cx + 12, panel.top + 94), (cx + 138, panel.top + 94), 1)

        options = self._setup_options(step)
        sel = self.setup_sel[step]
        font = get_font(S.FONT_UI_NAME, 23, bold=True)
        areas = []
        start_y = panel.top + 158
        for i, label in enumerate(options):
            rect = pygame.Rect(0, 0, min(430, panel.width - 70), 42)
            rect.center = (panel.centerx, start_y + i * 49)
            selected = i == sel
            accent = (255, 176, 74) if step == "difficulty" and selected else (55, 197, 220)
            pygame.draw.rect(surf, (21, 37, 49) if selected else (10, 23, 34), rect, border_radius=5)
            pygame.draw.rect(surf, accent if selected else (43, 66, 81), rect, width=2 if selected else 1, border_radius=5)
            if selected:
                pygame.draw.rect(surf, accent, (rect.left + 8, rect.top + 8, 4, rect.height - 16), border_radius=2)
            txt = font.render(label.upper(), True, (232, 241, 245) if selected else (155, 177, 190))
            surf.blit(txt, txt.get_rect(center=rect.center))
            areas.append(rect.inflate(6, 3))
        self.menu.register_hit_areas(areas)
        desc_font = get_font(S.FONT_UI_NAME, 15)
        desc = desc_font.render(self._setup_desc(step), True, (143, 170, 185))
        surf.blit(desc, desc.get_rect(center=(panel.centerx, min(panel.bottom - 62, start_y + len(options) * 49 + 16))))
        hint = get_font(S.FONT_UI_NAME, 13).render("ENTER AVANÇA  /  ESC OU CLIQUE DIREITO VOLTA", True, (100, 139, 157))
        surf.blit(hint, hint.get_rect(center=(panel.centerx, panel.bottom - 24)))
        self.menu.draw_cursor(surf)

    def _draw_pause_overlay(self, surf):
        overlay = pygame.Surface((S.WIDTH, S.HEIGHT), pygame.SRCALPHA)
        overlay.fill((1, 5, 10, 205))
        surf.blit(overlay, (0, 0))
        panel = pygame.Rect(0, 0, min(560, S.WIDTH - 48), 430)
        panel.center = (S.WIDTH // 2, S.HEIGHT // 2)
        self._draw_sci_panel(surf, panel, accent=(55, 197, 220), fill=(8, 18, 29), radius=12, border=2)
        font_title = get_font(S.FONT_TITLE_NAME, 38)
        title = font_title.render("SISTEMA PAUSADO", True, (225, 239, 245))
        surf.blit(title, title.get_rect(center=(panel.centerx, panel.top + 48)))
        pygame.draw.line(surf, (47, 91, 108), (panel.left + 45, panel.top + 82), (panel.right - 45, panel.top + 82), 1)
        font = get_font(S.FONT_UI_NAME, 20, bold=True)
        areas = []
        for i, item in enumerate(PAUSE_ITEMS):
            selected = i == self.pause_sel
            is_quit = item == "quit"
            accent = (255, 176, 74) if is_quit else (55, 197, 220)
            rect = pygame.Rect(0, 0, min(390, panel.width - 80), 42)
            rect.center = (panel.centerx, panel.top + 118 + i * 48)
            pygame.draw.rect(surf, (23, 39, 50) if selected else (10, 23, 34), rect, border_radius=5)
            pygame.draw.rect(surf, accent if selected else (42, 63, 77), rect, width=2 if selected else 1, border_radius=5)
            txt = font.render(self.pause_label(item), True, accent if selected else (177, 196, 207))
            surf.blit(txt, txt.get_rect(center=rect.center))
            areas.append(rect.inflate(5, 2))
        self.menu.register_hit_areas(areas)
        self.menu.draw_cursor(surf)

    # ------------------------------------------------------------ tela de configuração de controles (item 4)
    def _draw_keybinds_screen(self, surf):
        overlay = pygame.Surface((S.WIDTH, S.HEIGHT), pygame.SRCALPHA)
        overlay.fill((6, 6, 16, 225))
        surf.blit(overlay, (0, 0))

        panel = pygame.Rect(0, 0, 760, 560)
        panel.center = (S.WIDTH // 2, S.HEIGHT // 2)
        self._draw_sci_panel(surf, panel, accent=(55, 197, 220), fill=(9, 20, 31), radius=12, border=2)

        font_title = get_font(S.FONT_UI_NAME, 26, bold=True)
        title = font_title.render("CONFIGURAÇÃO DE CONTROLES", True, (240, 240, 250))
        surf.blit(title, title.get_rect(midtop=(panel.centerx, panel.top + 18)))

        # --- abas de jogador (JOGADOR 1 / 2 / 3 / 4), uma por jogador na partida atual
        n_players = max(1, len(self.players) or self.player_count)
        tab_font = get_font(S.FONT_UI_NAME, 15, bold=True)
        tab_w = (panel.width - 32) / n_players
        tab_areas = []
        for i in range(n_players):
            cfg = S.PLAYER_DEFS[i]
            tab_rect = pygame.Rect(panel.left + 16 + int(i * tab_w), panel.top + 58, int(tab_w) - 4, 34)
            active = i == self.keybinds_player
            col = S.hx(cfg["color"])
            bg = col if active else (40, 40, 56)
            pygame.draw.rect(surf, bg, tab_rect, border_radius=8)
            if not active:
                pygame.draw.rect(surf, col, tab_rect, width=2, border_radius=8)
            using_gp = self.input.player_uses_gamepad(i)
            label = cfg["short"] + (" 🎮" if using_gp else " ⌨")
            txt = tab_font.render(label, True, (10, 10, 18) if active else col)
            surf.blit(txt, txt.get_rect(center=tab_rect.center))
            tab_areas.append((tab_rect, i))

        gp_slot = self.input.bindings[self.keybinds_player].gamepad_slot
        gp = self.input.gamepad
        if gp_slot is not None and gp.is_connected(gp_slot):
            fam = gp.family(gp_slot)
            sub = get_font(S.FONT_UI_NAME, 13).render(
                f"Controle: {gp.name(gp_slot)} ({GP.FAMILY_NAMES[fam]})", True, (160, 200, 255))
        else:
            sub = get_font(S.FONT_UI_NAME, 13).render(
                "Usando teclado — aperte um botão do controle para associá-lo a este jogador",
                True, (160, 160, 180))
        surf.blit(sub, sub.get_rect(midtop=(panel.centerx, panel.top + 98)))

        # --- linhas de atalho: nome da ação à esquerda, caixa arredondada com a tecla/botão à direita
        row_font = get_font(S.FONT_UI_NAME, 19)
        key_font = get_font(S.FONT_UI_NAME, 17, bold=True)
        row_y0 = panel.top + 134
        row_h = 46
        row_areas = []
        fam = gp.family(gp_slot) if (gp_slot is not None and gp.is_connected(gp_slot)) else GP.XBOX
        for i, action in enumerate(REBIND_ACTIONS):
            ry = row_y0 + i * row_h
            row_rect = pygame.Rect(panel.left + 16, ry, panel.width - 32, row_h - 6)
            selected = (self.rebinding is None and i == getattr(self, "_keybinds_row", 0))
            if selected:
                pygame.draw.rect(surf, (21, 39, 51), row_rect, border_radius=6)
            if i > 0:
                pygame.draw.line(surf, (42, 65, 79), (row_rect.left, ry - 3), (row_rect.right, ry - 3), 1)

            label = row_font.render(REBIND_ACTION_LABELS[action], True, (230, 230, 240))
            surf.blit(label, (row_rect.left + 14, row_rect.centery - label.get_height() // 2))

            # caixa da tecla (estilo "key cap" arredondado, como na referência)
            key_label = self.input.key_display(self.keybinds_player, action)
            is_capturing = self.rebinding == (self.keybinds_player, i)
            box_w = max(54, key_font.size(key_label)[0] + 26)
            box = pygame.Rect(0, 0, box_w, 32)
            box.midright = (row_rect.right - 170, row_rect.centery)
            box_col = (75, 53, 23) if is_capturing else (19, 34, 46)
            pygame.draw.rect(surf, box_col, box, border_radius=8)
            pygame.draw.rect(surf, (65, 101, 120) if not is_capturing else (255, 176, 74), box, width=2,
                              border_radius=8)
            ktxt = key_font.render("..." if is_capturing else key_label, True, (240, 240, 250))
            surf.blit(ktxt, ktxt.get_rect(center=box.center))

            # botão do controle equivalente (ícone colorido no padrão da família detectada)
            btn_name = S.GAMEPAD_BUTTONS.get(action)
            if btn_name:
                blabel = GP.button_label(btn_name, fam)
                bcolor = S.hx(GP.button_color(btn_name, fam))
                bcircle = pygame.Rect(0, 0, 32, 32)
                bcircle.midright = (row_rect.right - 16, row_rect.centery)
                pygame.draw.circle(surf, bcolor, bcircle.center, 15)
                pygame.draw.circle(surf, (20, 20, 28), bcircle.center, 15, width=2)
                bt = get_font(S.FONT_UI_NAME, 13, bold=True).render(blabel, True, (20, 20, 28))
                surf.blit(bt, bt.get_rect(center=bcircle.center))

            row_areas.append(row_rect)

        # --- rodapé: Restaurar Padrões / Voltar
        foot_y = row_y0 + len(REBIND_ACTIONS) * row_h + 18
        foot_font = get_font(S.FONT_UI_NAME, 20, bold=True)
        reset_rect = pygame.Rect(0, 0, 240, 42)
        reset_rect.midleft = (panel.left + 40, foot_y + 20)
        back_rect = pygame.Rect(0, 0, 160, 42)
        back_rect.midright = (panel.right - 40, foot_y + 20)
        reset_sel = self.rebinding is None and getattr(self, "_keybinds_row", 0) == len(REBIND_ACTIONS)
        back_sel = self.rebinding is None and getattr(self, "_keybinds_row", 0) == len(REBIND_ACTIONS) + 1
        pygame.draw.rect(surf, (60, 40, 20) if reset_sel else (40, 40, 56), reset_rect, border_radius=10)
        pygame.draw.rect(surf, (255, 180, 90) if reset_sel else (90, 90, 110), reset_rect, width=2, border_radius=10)
        rtxt = foot_font.render("RESTAURAR PADRÕES", True, (255, 220, 180) if reset_sel else (210, 210, 220))
        surf.blit(rtxt, rtxt.get_rect(center=reset_rect.center))
        pygame.draw.rect(surf, (20, 60, 40) if back_sel else (40, 40, 56), back_rect, border_radius=10)
        pygame.draw.rect(surf, (120, 230, 160) if back_sel else (90, 90, 110), back_rect, width=2, border_radius=10)
        btxt = foot_font.render("VOLTAR", True, (200, 255, 220) if back_sel else (210, 210, 220))
        surf.blit(btxt, btxt.get_rect(center=back_rect.center))
        row_areas.append(reset_rect)
        row_areas.append(back_rect)

        self.menu.register_hit_areas(row_areas)
        # abas de jogador usam índices negativos (-1, -2, ...) para não colidir com as linhas de ação acima
        self.menu.register_extra_hit_areas([(rect, -(i + 1)) for rect, i in tab_areas])

        hint = get_font(S.FONT_UI_NAME, 14).render(
            "←/→ troca de jogador · ENTER remapeia · ESC/clique direito volta", True, (150, 150, 170))
        surf.blit(hint, hint.get_rect(midbottom=(panel.centerx, panel.bottom - 10)))
        self.menu.draw_cursor(surf)

    def _draw_gameover(self, surf):
        overlay = pygame.Surface((S.WIDTH, S.HEIGHT), pygame.SRCALPHA)
        overlay.fill((1, 5, 10, 210))
        surf.blit(overlay, (0, 0))
        panel = pygame.Rect(0, 0, min(620, S.WIDTH - 48), 300)
        panel.center = (S.WIDTH // 2, S.HEIGHT // 2)
        accent = (91, 220, 177) if self.victory else (255, 112, 91)
        self._draw_sci_panel(surf, panel, accent=accent, fill=(8, 18, 29), radius=12, border=3)
        font_title = get_font(S.FONT_TITLE_NAME, 46)
        msg = "MISSÃO CONCLUÍDA" if self.victory else "FIM DE JOGO"
        txt = font_title.render(msg, True, (228, 239, 244))
        surf.blit(txt, txt.get_rect(center=(panel.centerx, panel.top + 70)))
        pygame.draw.line(surf, accent, (panel.left + 65, panel.top + 108), (panel.right - 65, panel.top + 108), 1)
        if self.winner is not None:
            font = get_font(S.FONT_UI_NAME, 23, bold=True)
            w = font.render(f"{self.winner.name} venceu", True, self.winner.color)
            surf.blit(w, w.get_rect(center=(panel.centerx, panel.top + 148)))
        elif len(self.players) > 1:
            font = get_font(S.FONT_UI_NAME, 23, bold=True)
            w = font.render("EMPATE", True, (205, 220, 228))
            surf.blit(w, w.get_rect(center=(panel.centerx, panel.top + 148)))
        if self.gameover_t > S.GAMEOVER_INPUT_LOCK:
            hint = get_font(S.FONT_UI_NAME, 15).render("ENTER / CLIQUE / A NO CONTROLE: VER ESTATÍSTICAS", True, (131, 163, 179))
            surf.blit(hint, hint.get_rect(center=(panel.centerx, panel.bottom - 35)))

    # ------------------------------------------------------------ tela de MVP / resumo (item 6)
    def _draw_mvp_screen(self, surf):
        """Tela final com destaque para o MVP e classificação legível de todos os jogadores."""
        # Fundo escurecido para separar os resultados do cenário da partida.
        overlay = pygame.Surface((S.WIDTH, S.HEIGHT), pygame.SRCALPHA)
        overlay.fill((3, 8, 15, 242))
        surf.blit(overlay, (0, 0))

        title_font = get_font(S.FONT_TITLE_NAME, 38, bold=True)
        subtitle_font = get_font(S.FONT_UI_NAME, 13, bold=True)
        header_font = get_font(S.FONT_UI_NAME, 13, bold=True)
        name_font = get_font(S.FONT_UI_NAME, 19, bold=True)
        value_font = get_font(S.FONT_UI_NAME, 18, bold=True)
        detail_font = get_font(S.FONT_UI_NAME, 13)
        small_font = get_font(S.FONT_UI_NAME, 11, bold=True)

        accent = S.hx("#ffb04a") if self.victory else S.hx("#e66c78")
        header = "VITÓRIA!" if self.victory else "FIM DE JOGO"
        title = title_font.render(header, True, (238, 246, 252))
        surf.blit(title, title.get_rect(center=(S.WIDTH // 2, 35)))
        subtitle = subtitle_font.render("RELATÓRIO DA PARTIDA  /  CLASSIFICAÇÃO GERAL", True, (105, 160, 180))
        surf.blit(subtitle, subtitle.get_rect(center=(S.WIDTH // 2, 65)))

        # Cartão de MVP em destaque, sem depender apenas de cor ou emoji.
        top = 84
        hero_h = 76
        hero = pygame.Rect(max(24, S.WIDTH // 2 - 330), top, min(660, S.WIDTH - 48), hero_h)
        pygame.draw.rect(surf, (13, 25, 37), hero, border_radius=12)
        pygame.draw.rect(surf, accent, hero, width=2, border_radius=12)
        pygame.draw.rect(surf, accent, pygame.Rect(hero.left + 1, hero.top + 10, 4, hero_h - 20), border_radius=2)
        if self.mvp is not None:
            mvp_label = small_font.render("MVP DA PARTIDA", True, accent)
            surf.blit(mvp_label, mvp_label.get_rect(midtop=(hero.centerx, hero.top + 9)))
            mvp_name = name_font.render(self.mvp.name, True, self.mvp.color)
            surf.blit(mvp_name, mvp_name.get_rect(midtop=(hero.centerx, hero.top + 26)))
            mvp_stats = detail_font.render(
                f"{self.mvp.score} pontos    •    {self.mvp.kills} abates", True, (203, 220, 231))
            surf.blit(mvp_stats, mvp_stats.get_rect(midtop=(hero.centerx, hero.top + 52)))
        else:
            empty = name_font.render("Nenhum MVP definido", True, (180, 196, 208))
            surf.blit(empty, empty.get_rect(center=hero.center))

        # Classificação ordenada por pontuação e, em caso de empate, por abates.
        players = sorted(self.players, key=lambda p: (p.score, p.kills), reverse=True)
        table_x = max(24, int(S.WIDTH * 0.055))
        table_w = min(S.WIDTH - 48, int(S.WIDTH * 0.89))
        table_y = top + hero_h + 14
        footer_h = 42
        table_bottom = S.HEIGHT - footer_h - 10
        table_h = max(160, table_bottom - table_y)
        header_h = 38
        row_h = max(42, min(76, (table_h - header_h) // max(1, len(players))))
        # Limita a tabela à área útil; o detalhe por tipo é compacto para muitos jogadores.
        table_rect = pygame.Rect(table_x, table_y, table_w, min(table_h, header_h + row_h * max(1, len(players))))
        pygame.draw.rect(surf, (8, 17, 28), table_rect, border_radius=10)
        pygame.draw.rect(surf, (38, 68, 83), table_rect, width=1, border_radius=10)
        pygame.draw.rect(surf, (17, 35, 48), pygame.Rect(table_x + 1, table_y + 1, table_w - 2, header_h), border_radius=8)

        # Colunas proporcionais à largura disponível para continuar legível em outras resoluções.
        col_rank = int(table_w * 0.08)
        col_player = int(table_w * 0.32)
        col_score = int(table_w * 0.16)
        col_kills = int(table_w * 0.14)
        col_types = table_w - col_rank - col_player - col_score - col_kills
        starts = [table_x, table_x + col_rank, table_x + col_rank + col_player,
                  table_x + col_rank + col_player + col_score,
                  table_x + col_rank + col_player + col_score + col_kills]
        headers = [("#", col_rank), ("JOGADOR", col_player), ("PONTOS", col_score),
                   ("ABATES", col_kills), ("ABATES POR TIPO", col_types)]
        for idx, (label, width) in enumerate(headers):
            txt = header_font.render(label, True, (132, 177, 194))
            surf.blit(txt, txt.get_rect(midleft=(starts[idx] + 14, table_y + header_h // 2)))

        for i, player in enumerate(players):
            ry = table_y + header_h + i * row_h
            if ry + row_h > table_rect.bottom:
                break
            row_rect = pygame.Rect(table_x + 1, ry, table_w - 2, row_h)
            is_mvp = player is self.mvp
            row_bg = (26, 34, 37) if is_mvp else ((12, 25, 36) if i % 2 == 0 else (10, 21, 31))
            pygame.draw.rect(surf, row_bg, row_rect)
            if is_mvp:
                pygame.draw.rect(surf, S.hx("#ffb04a"), pygame.Rect(row_rect.left, ry + 7, 3, row_h - 14), border_radius=2)
            else:
                pygame.draw.rect(surf, player.color, pygame.Rect(row_rect.left, ry + 9, 3, row_h - 18), border_radius=2)
            pygame.draw.line(surf, (27, 48, 61), (row_rect.left + 8, ry + row_h - 1),
                             (row_rect.right - 8, ry + row_h - 1), 1)

            # Colocação numerada e destaque discreto para os três primeiros.
            rank_color = (255, 190, 91) if i == 0 else ((173, 205, 218) if i < 3 else (100, 132, 148))
            rank_text = value_font.render(f"{i + 1:02d}", True, rank_color)
            surf.blit(rank_text, rank_text.get_rect(center=(starts[0] + col_rank // 2, ry + row_h // 2)))

            player_name = player.name
            max_name_w = max(40, col_player - 28)
            while player_name and name_font.size(player_name)[0] > max_name_w:
                player_name = player_name[:-1]
            if player_name != player.name and len(player_name) > 2:
                player_name = player_name[:-2] + "…"
            name_txt = name_font.render(player_name, True, player.color)
            surf.blit(name_txt, name_txt.get_rect(midleft=(starts[1] + 14, ry + row_h // 2)))
            if is_mvp:
                tag = small_font.render("MVP", True, S.hx("#ffb04a"))
                tag_x = min(starts[1] + col_player - tag.get_width() - 10,
                            starts[1] + 14 + name_txt.get_width() + 8)
                surf.blit(tag, tag.get_rect(midleft=(tag_x, ry + row_h // 2)))

            score_txt = value_font.render(f"{player.score:,}".replace(",", "."), True, (238, 245, 250))
            surf.blit(score_txt, score_txt.get_rect(center=(starts[2] + col_score // 2, ry + row_h // 2)))
            kills_txt = value_font.render(str(player.kills), True, (190, 222, 235))
            surf.blit(kills_txt, kills_txt.get_rect(center=(starts[3] + col_kills // 2, ry + row_h // 2)))

            by_type = sorted(((k, v) for k, v in player.kills_by_type.items() if v > 0),
                             key=lambda kv: (-kv[1], str(kv[0])))
            if by_type:
                parts = []
                for kind, count in by_type[:3]:
                    label = S.ENEMY_TYPES.get(kind, {}).get("label", str(kind))
                    parts.append(f"{label} {count}")
                if len(by_type) > 3:
                    parts.append(f"+{len(by_type) - 3} tipos")
                detail = "  ·  ".join(parts)
            else:
                detail = "Sem abates registrados"
            # Recorta o texto de tipos em vez de deixar invadir a coluna vizinha.
            max_detail_w = max(20, col_types - 24)
            while detail and detail_font.size(detail)[0] > max_detail_w:
                detail = detail[:-2] + "…" if len(detail) > 2 else ""
                if detail_font.size(detail)[0] <= max_detail_w:
                    break
            detail_txt = detail_font.render(detail, True, (153, 181, 194))
            surf.blit(detail_txt, detail_txt.get_rect(midleft=(starts[4] + 12, ry + row_h // 2)))

        hint = get_font(S.FONT_UI_NAME, 14, bold=True).render(
            "ENTER  REINICIAR     ·     M  NOVA PARTIDA     ·     Q  MENU INICIAL",
            True, (151, 181, 195))
        surf.blit(hint, hint.get_rect(center=(S.WIDTH // 2, S.HEIGHT - 22)))

    @property
    def collisions(self):
        if not hasattr(self, "_collisions"):
            self._collisions = CollisionManager(self)
        return self._collisions
