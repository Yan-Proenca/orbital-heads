"""
settings.py — todas as constantes ajustáveis do jogo.

Migrado de main.py (Tkinter), 1:1 nos valores de jogo (física, armas,
boosts, rounds, chefes). Cores continuam como strings hex "#rrggbb" (como
no original) e são convertidas para tuplas RGB sob demanda por hx().
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(BASE_DIR, "assets")
SFX_DIR = os.path.join(ASSET_DIR, "sfx")
MUSIC_DIR = os.path.join(ASSET_DIR, "music")
FONT_DIR = os.path.join(ASSET_DIR, "fonts")


def hx(c):
    """'#rrggbb' -> (r, g, b). Aceita já-tupla (passa direto)."""
    if isinstance(c, tuple):
        return c
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


# ----------------------------------------------------------------- janela
WIDTH, HEIGHT = 1280, 720
FPS = 60
MAX_DT = 0.05
HUD_H = 78
GROUND_Y = 650
DANGER_Y = 560
ARENA_MARGIN = 16

# ----------------------------------------------------------------- jogador
PLAYER_LIVES = 3
PLAYER_SPEED = 380.0
PLAYER_ACCEL = 3800.0
PLAYER_AIR_ACCEL = 2600.0
PLAYER_FRICTION = 4600.0
GRAVITY = 2300.0
JUMP_SPEED = 800.0
MAX_FALL = 1400.0
INVULN_TIME = 2.0
RESPAWN_DELAY = 0.9

FIRE_INTERVAL = 0.17
BULLET_SPEED = 980.0
MAX_BULLETS_PER_PLAYER = 8

DASH_DURATION = 0.20
DASH_SPEED = 1300.0
DASH_COOLDOWN = 4.0
DASH_INVULNERABLE = True

# ----------------------------------------------------------------- inimigos (fiel ao main.py original)
ENEMY_TYPES = {
    "drone": dict(label="Drone", w=36, h=30, hit_w=30, hit_h=24, hp=1, hp_growth=0.20,
                  points=100, speed=105.0, pitch_x=58, pitch_y=50, per_row=13, size=34,
                  fx=("#fff2a8", "#ff3d71", ("#ff3d71", "#ffd23f", "#ffffff"))),
    "ship": dict(label="Nave", w=56, h=40, hit_w=48, hit_h=32, hp=3, hp_growth=0.34,
                 points=250, speed=80.0, pitch_x=88, pitch_y=62, per_row=9, size=48,
                 fx=("#e8d8ff", "#8e5bff", ("#8e5bff", "#7ff3ff", "#ffffff"))),
    "machine": dict(label="Máquina", w=92, h=64, hit_w=84, hit_h=56, hp=10, hp_growth=0.60,
                     points=500, speed=46.0, pitch_x=124, pitch_y=84, per_row=6, size=84,
                     fx=("#ffe0a0", "#ff5a36", ("#ff8a1f", "#ffd23f", "#8d9bc2", "#ffffff"))),
    "mini": dict(label="Mini-nave", w=44, h=31, hit_w=38, hit_h=26, hp=2, hp_growth=0.0, points=150,
                 speed=125.0, size=36, sprite_scale=0.78,
                 fx=("#e8d8ff", "#8e5bff", ("#8e5bff", "#7ff3ff", "#ffffff"))),
    "miniboss": dict(label="Miniboss", w=150, h=104, hit_w=132, hit_h=88, hp=70, hp_growth=0.0, points=3000, size=150,
                      fx=("#ffe0a0", "#ff5a36", ("#ff5a36", "#ffd23f", "#8d9bc2", "#ffffff"))),
    "mothership": dict(label="Nave-mãe", w=176, h=84, hit_w=156, hit_h=70, hp=60, hp_growth=0.0, points=2000, size=150,
                        fx=("#e8d8ff", "#8e5bff", ("#8e5bff", "#7ff3ff", "#ff7ad9", "#ffffff"))),
    "finalboss": dict(label="Chefe final", w=224, h=128, hit_w=196, hit_h=108, hp=150, hp_growth=0.0, points=10000,
                       size=220, fx=("#ffffff", "#ff2a4d", ("#ff2a4d", "#ffd23f", "#ff7ad9", "#ffffff"))),
    "car": dict(label="Carro", w=132, h=46, hit_w=126, hit_h=46, hp=2, hp_growth=0.0, points=800, size=90,
                fx=("#ffe0a0", "#ff9a3c", ("#ff9a3c", "#ffd23f", "#8d9bc2", "#ffffff"))),
    "jet": dict(label="Jato", w=88, h=34, hit_w=78, hit_h=26, hp=6, hp_growth=0.35, points=400, speed=250.0, size=70,
                fx=("#e0f6ff", "#37c8ff", ("#37c8ff", "#ffffff", "#8d9bc2"))),
    "jetbomb": dict(label="Bomba", points=50),
}
STANDARD_KINDS = ("drone", "ship", "machine")
ENEMY_ORDER = ("machine", "ship", "drone")
COUNT_ORDER = ("drone", "ship", "machine")
SHOT_DAMAGE = 1
ENEMY_CLASSES_KINDS = ("drone", "ship", "machine", "mini")

ROUNDS_TO_WIN = 10      # default/fallback; o valor real por partida é GAME_MODES[modo]["rounds_to_win"]
ROUND_TABLE = {
    1: (8, 10, 0), 2: (12, 12, 3), 3: (12, 14, 4), 4: (10, 16, 4), 5: (0, 10, 4),
    6: (0, 14, 4), 7: (0, 14, 4), 8: (0, 16, 4), 9: (0, 10, 6), 10: (0, 10, 5),
}
ENDLESS_BASE_ROUND = 3
GROWTH_PER_ROUND = (2, 2, 1)
MAX_COUNTS = (26, 18, 6)
SPEED_GROWTH_PER_ROUND = 0.07
MAX_SPEED_FACTOR = 2.2
ROUND_INTRO_TIME = 2.2
ROUND_CLEAR_TIME = 2.2
EDGE_MARGIN = 14
DESCENT_STEP = 22.0
DESCENT_SPEED = 150.0
ENTRY_DROP = 210.0

BOMB_FIRST_DELAY = 1.9
BOMB_INTERVAL_BASE = 2.0
BOMB_INTERVAL_DECAY = 0.16
BOMB_INTERVAL_MIN = 0.7
BOMB_SPEED = 260.0
BOMB_SPEED_GROWTH = 12.0
DRONE_BOMB_ROUND = 1

BREACH_COOLDOWN = 1.5
BREACH_CLEAR_MARGIN = 40

# ----------------------------------------------------------------- desempenho
MAX_PARTICLES = 200
MIN_PARTICLES = 60
PERF_EMA = 0.08
USE_SPATIAL_GRID = True
GRID_CELL = 96
GRID_MIN_PAIRS = 120
FPS_LOD_MEDIUM = 48
FPS_LOD_LOW = 32
GAMEOVER_INPUT_LOCK = 1.2

# ----------------------------------------------------------------- aparência
FONT_UI_NAME = "consolas"
FONT_TITLE_NAME = "impact"
OUTLINE = "#0a0d20"

# ----------------------------------------------------------------- jogadores
# Suporta de 1 a 4 jogadores (MAX_PLAYERS). Os dois primeiros mantêm os
# atalhos de teclado clássicos (WASD+espaço / setas+enter); P3 e P4 vêm com
# um segundo par de atalhos de teclado (pouco prático em conjunto com os
# outros dois no mesmo teclado — pensados para quem vai jogar com controle,
# que é o uso esperado para 3º/4º jogador) e todos podem receber um
# controle via InputManager.assign_joystick()/GamepadManager.
MIN_PLAYERS = 1
MAX_PLAYERS = 4
DEFAULT_PLAYER_COUNT = 2

PLAYER_DEFS = [
    dict(name="JOGADOR 1", short="P1", color="#37c8ff", dark="#0b6a99", light="#c7f4ff",
         visor="#ffffff", bullet="#9ff0ff", bullet_core="#ffffff", spawn_x_frac=0.20, facing=1,
         key_names=dict(left="a", right="d", jump="w", dash="s", fire="space"),
         labels=(("A / D", "mover"), ("W", "pular"), ("S", "dash"), ("ESPAÇO", "atirar para cima"))),
    dict(name="JOGADOR 2", short="P2", color="#ff9a3c", dark="#a4500b", light="#ffe2c4",
         visor="#fff3c4", bullet="#ffd27a", bullet_core="#fff6d8", spawn_x_frac=0.40, facing=-1,
         key_names=dict(left="left", right="right", jump="up", dash="down", fire="return"),
         labels=(("← / →", "mover"), ("↑", "pular"), ("↓", "dash"), ("ENTER", "atirar para cima"))),
    dict(name="JOGADOR 3", short="P3", color="#46f08a", dark="#0b7a45", light="#c8ffe0",
         visor="#e8fff0", bullet="#8dffc0", bullet_core="#ffffff", spawn_x_frac=0.60, facing=1,
         key_names=dict(left="j", right="l", jump="i", dash="k", fire="o"),
         labels=(("J / L", "mover"), ("I", "pular"), ("K", "dash"), ("O", "atirar para cima"))),
    dict(name="JOGADOR 4", short="P4", color="#b07cff", dark="#5a2e99", light="#e8d8ff",
         visor="#f3e8ff", bullet="#d8b8ff", bullet_core="#ffffff", spawn_x_frac=0.80, facing=-1,
         key_names=dict(left="kp4", right="kp6", jump="kp8", dash="kp5", fire="kp0"),
         labels=(("4 / 6 (num.)", "mover"), ("8 (num.)", "pular"), ("5 (num.)", "dash"), ("0 (num.)", "atirar"))),
]

ROUND_NOTES = {1: "Um enxame de drones se aproxima",
               2: "Naves de combate detectadas",
               3: "Máquinas voadoras pesadas na área"}
DEFAULT_NOTE = "Ondas mistas: mais rápidas e resistentes"

# ----------------------------------------------------------------- dificuldade
DIFFICULTY_ORDER = ("easy", "normal", "hard", "extreme")
DEFAULT_DIFFICULTY = "normal"
DIFFICULTIES = {
    "easy": dict(label="FÁCIL", color="#46f08a", enemy_speed=0.75, enemy_hp=0.75, proj_speed=0.80,
                 drop_chance=0.45, good_ratio=0.75,
                 desc="Mais oportunidades de recuperação: inimigos lentos e frágeis e muitos boosts positivos."),
    "normal": dict(label="MÉDIO", color="#37c8ff", enemy_speed=1.00, enemy_hp=1.00, proj_speed=1.00,
                   drop_chance=0.35, good_ratio=0.60,
                   desc="A experiência de referência: equilíbrio entre desafio e recompensa."),
    "hard": dict(label="DIFÍCIL", color="#ffb02e", enemy_speed=1.25, enemy_hp=1.40, proj_speed=1.25,
                 drop_chance=0.25, good_ratio=0.45,
                 desc="Inimigos mais rápidos e resistentes; boosts raros e quase metade são armadilhas."),
    "extreme": dict(label="EXTREMO", color="#ff2a4d", enemy_speed=1.55, enemy_hp=1.90, proj_speed=1.50,
                     drop_chance=0.15, good_ratio=0.30,
                     desc="Inimigos muito resistentes e velozes, tiros rápidos e poucos boosts positivos."),
}

# ----------------------------------------------------------------- modo de jogo
# "classic": os 10 rounds originais, cada um com composição fixa (ROUND_TABLE)
#            e os encontros especiais de ROUND_SPECIALS (miniboss, nave-mãe,
#            carro, jatos, chefe final no round 10) — vitória ao limpar o 10.
# "endless": os mesmos 10 primeiros rounds, seguidos por rounds extras
#            gerados proceduralmente (wave_counts() já cresce a composição
#            após ENDLESS_BASE_ROUND) até ENDLESS_ROUNDS_TO_WIN; os
#            encontros especiais do 5 ao 10 ainda acontecem nessas posições,
#            mas não se repetem depois — do round 11 em diante é só a
#            progressão padrão (drones/naves/máquinas), cada vez mais forte.
GAME_MODE_ORDER = ("classic", "endless")
DEFAULT_GAME_MODE = "classic"
GAME_MODES = {
    "classic": dict(label="CLÁSSICO", rounds_to_win=10,
                     desc="A campanha original: 10 rounds, terminando no Chefe Final."),
    "endless": dict(label="ONDAS INFINITAS", rounds_to_win=50,
                     desc="Até 50 rounds: a campanha clássica seguida de ondas cada vez mais difíceis."),
}

# ----------------------------------------------------------------- armas
WEAPONS = {
    "standard": dict(name="PADRÃO", damage=1.0, speed=BULLET_SPEED, interval=FIRE_INTERVAL, count=1, spread=0.0,
                      max_proj=MAX_BULLETS_PER_PLAYER, range=None, color=None, style="bullet", w=6, h=24, weight=1.0,
                      muzzle=0.07),
    "machinegun": dict(name="METRALHADORA", damage=0.5, speed=1100.0, interval=0.075, count=1, spread=0.0,
                        max_proj=16, range=None, color="#ffe14d", style="tracer", w=4, h=14, weight=3.0, muzzle=0.09),
    "rifle": dict(name="FUZIL", damage=3.0, speed=1500.0, interval=0.50, count=1, spread=0.0,
                  max_proj=5, range=None, color="#7ff3ff", style="beam", w=8, h=42, weight=3.0, muzzle=0.12),
    "shotgun": dict(name="ESCOPETA", damage=0.75, speed=900.0, interval=0.42, count=3, spread=28.0,
                     max_proj=12, range=640.0, color="#ff8a1f", style="pellet", w=8, h=8, weight=3.0, muzzle=0.10),
}
WEAPON_ORDER = ("standard", "machinegun", "rifle", "shotgun")
WEAPON_RESET_ON_DEATH = True

# ----------------------------------------------------------------- boosts
BOOSTS = {
    "shield": dict(name="INVENCIBILIDADE", chip="INVENCÍVEL", good=True, duration=5.0, scope="player",
                    color="#46f08a", icon="S"),
    "slow_foes": dict(name="LENTIDÃO DAS NAVES", chip="NAVES LENTAS", good=True, duration=5.0, scope="global",
                       color="#37c8ff", icon="L", enemy_move=0.5, enemy_proj=0.5, enemy_attack=0.5),
    "haste": dict(name="VELOCIDADE", chip="VELOCIDADE", good=True, duration=10.0, scope="player",
                   color="#ffe14d", icon="V", speed=1.5),
    "fast_foes": dict(name="NAVES ACELERADAS", chip="NAVES RÁPIDAS", good=False, duration=6.0, scope="global",
                       color="#ff4d6d", icon="N", enemy_move=1.45, enemy_proj=1.30, enemy_attack=1.35),
    "slow_self": dict(name="LENTIDÃO", chip="LENTIDÃO", good=False, duration=3.0, scope="player",
                       color="#b07cff", icon="P", speed=0.5),
    "slow_gun": dict(name="ARMA LENTA", chip="ARMA LENTA", good=False, duration=5.0, scope="player",
                      color="#ff9a3c", icon="A", fire_interval=1.8),
}
GOOD_BOOSTS = ("shield", "slow_foes", "haste")
BAD_BOOSTS = ("fast_foes", "slow_self", "slow_gun")
PLAYER_SPEED_MULT_LIMITS = (0.35, 2.0)
FIRE_INTERVAL_MULT_LIMITS = (0.5, 3.0)
ENEMY_MULT_LIMITS = (0.4, 2.0)
BOSS_EFFECT_SCALE = 0.5

PICKUP_LIFETIME = 3.0
WEAPON_PICKUP_LIFETIME = 8.0
PICKUP_FALL_SPEED = 170.0
MAX_PICKUPS = 5
DROP_COOLDOWN = 1.0
MAX_DROPS_PER_ROUND = 8
WEAPON_DROP_CHANCE = 0.07
DROP_SOURCE_MULT = {"drone": 0.30, "ship": 0.60, "machine": 1.20, "mini": 0.60, "jet": 1.50, "jetbomb": 0.50,
                     "car": 2.50, "miniboss": 3.00, "mothership": 3.00, "finalboss": 0.0}

# ----------------------------------------------------------------- chefes e especiais
BOSS_INTRO_TIME = 2.4
BOSS_DEATH_TIME = 1.5
ROUND_SPECIALS = {
    5: dict(kind="miniboss", formation_y=228, descent_scale=0.6, intro=3.2, title="MINIBOSS DETECTADO"),
    6: dict(kind="mothership", formation_y=208, descent_scale=0.6, intro=3.2, title="NAVE-MÃE DETECTADA"),
    7: dict(kind="car", formation_y=None, descent_scale=1.0, intro=3.0, title="CARRO CIBERNÉTICO NA PISTA", speed_mult=1.0),
    8: dict(kind="car", formation_y=None, descent_scale=1.0, intro=3.0, title="CARRO CIBERNÉTICO: MODO TURBO",
            speed_mult=1.35, turbo=True),
    9: dict(kind="jets", formation_y=170, descent_scale=0.8, intro=3.0, title="JATOS E BOMBAS DESTRUTÍVEIS"),
    10: dict(kind="finalboss", formation_y=250, descent_scale=0.5, intro=3.4, title="CHEFE FINAL"),
}
MINIBOSS = dict(base_y=150, amplitude=420, speed=0.55, first_attack=1.4,
                 rocket_interval=3.6, rocket_count=2, rocket_speed=140.0, rocket_omega=4.2, rocket_radius=(10.0, 60.0),
                 rocket_grow=2.5, rain_interval=2.7, rain_speed=300.0, rain_spread=0.40, rain_stagger=0.15)
MOTHERSHIP = dict(base_y=150, amplitude=440, speed=0.45, first_attack=1.5, shot_interval=2.0, shot_speed=300.0,
                   burst_interval=5.5, burst_count=9, burst_speed=230.0, split=(4, 7))
FINALBOSS = dict(base_y=172, amplitude=430, speed=0.50, first_attack=1.6, interval=1.9, bullet_speed=300.0,
                  regen_time=3.4, regen_fraction=0.65,
                  frenzy_speed_mult=1.6, frenzy_interval_mult=0.55, min_interval=0.6,
                  orb_fuse=1.9, orb_radius=115.0, orb_speed=210.0, orb_warn=0.9)
CAR = dict(speed=190.0, impacts=3, stomp_lock=0.3, spark_interval=0.07, turbo_mult=2.0,
           turbo_every=(3.0, 4.5), turbo_time=0.9)
JET = dict(count=2, lanes=(250, 470), bomb_interval=1.0, away_time=(1.2, 2.6), bomb_vx_factor=0.3, first_delay=(0.5, 2.0))
JET_BOMB = dict(hp=3, speed=190.0, ground_radius=110.0, air_radius=50.0)
MINI_FIRE_INTERVAL = (2.2, 3.4)
MINI_BULLET_SPEED = 260.0
MAX_HOSTILE_PROJECTILES = 90

# ----------------------------------------------------------------- áudio
DEFAULT_MUSIC_VOLUME = 0.5
DEFAULT_SFX_VOLUME = 0.8

SFX_FILES = {
    "shoot": "shoot.ogg",
    "shoot_rifle": "shoot_rifle.ogg",
    "shoot_shotgun": "shoot_shotgun.ogg",
    "explosion_small": "explosion_small.ogg",
    "explosion_big": "explosion_big.ogg",
    "player_hit": "player_hit.ogg",
    "player_death": "player_death.ogg",
    "pickup_boost_good": "pickup_good.ogg",
    "pickup_boost_bad": "pickup_bad.ogg",
    "pickup_weapon": "pickup_weapon.ogg",
    "dash": "dash.ogg",
    "jump": "jump.ogg",
    "menu_move": "menu_move.ogg",
    "menu_confirm": "menu_confirm.ogg",
    "round_clear": "round_clear.ogg",
    "boss_warning": "boss_warning.ogg",
    "victory": "victory.ogg",
    "gameover": "gameover.ogg",
    "breach": "breach.ogg",
}
MUSIC_FILES = {
    "title": "title_theme.ogg",
    "gameplay": "gameplay_theme.ogg",
    "boss": "boss_theme.ogg",
    "victory": "victory_theme.ogg",
}

# ----------------------------------------------------------------- controles (joystick)
# Os NOMES abaixo ("a", "b", "x", "y", "lb", "rb", "start", "back") são os
# nomes lógicos já normalizados pelo gamepad.GamepadManager — ele mesmo
# resolve o índice físico certo por família de controle (Xbox, PlayStation,
# Switch, genérico), então aqui não lidamos mais com índices numéricos.
JOYSTICK_DEADZONE = 0.35
GAMEPAD_BUTTONS = dict(jump="a", dash="b", fire="x", pause="start", confirm="a", back="b")
GAMEPAD_AXIS_X = 0          # analógico esquerdo, eixo horizontal
GAMEPAD_AXIS_Y = 1          # analógico esquerdo, eixo vertical (navegação de menu)
MENU_AXIS_REPEAT_DELAY = 0.35   # 1º passo do analógico/d-pad no menu
MENU_AXIS_REPEAT_RATE = 0.16    # passos seguintes enquanto mantém segurado

# Cor da luz (barra de luz do PS4/PS5) atribuída a cada vaga de jogador,
# para quem estiver usando controle com LED — puramente estético.
GAMEPAD_LED_COLORS = ["#37c8ff", "#ff9a3c", "#46f08a", "#b07cff"]
