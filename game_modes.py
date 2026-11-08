"""
game_modes.py — modos de SOBREVIVÊNCIA (settings.SURVIVAL_GAME_MODES): Rockets Sky, Ball Rain,
Mechanic Room e Crazy Car. Nenhum deles reimplementa física/colisão: cada um é um ModeManager fino
que pilota os objetos que já existem (WaveManager/HazardManager/Rocket/BallPod/BouncingSphere/CyberCar),
decidindo só O QUÊ e QUANDO nasce, e lendo o progresso (nível/round/onda) para o HUD e a tela de game over.

Como se encaixa em game.py:
  - Game.start_match() cria self.wave (WaveManager) normalmente — collisions.py e player.py dependem
    dele (g.wave.enemies / g.wave.hazards / g.wave.cars) para QUALQUER modo, então ele nunca é substituído.
  - Quando o modo é de sobrevivência, Game também cria self.mode_runner = <Mode>Manager(game).
    Game.update() chama self.mode_runner.update(dt) ANTES de self.wave.update(dt) (ver integração em
    game.py); fora isso, o loop principal não muda.
  - self.mode_runner.hud_lines() alimenta o HUD (mesmo formato que WaveManager.hazards.hud_lines():
    lista de (texto, cor)); self.mode_runner.result_lines() alimenta a tela de game over.
  - A condição de derrota ("todos os jogadores eliminados" -> end_match(False)) já é genérica em
    Game.update() e não muda: nenhum modo de sobrevivência "vence", só sobrevive o quanto der.

Todas as constantes de balanceamento ficam em settings.py (bloco "MODOS DE SOBREVIVÊNCIA"); este
arquivo só orquestra.
"""
import random

import settings as S
from utils import clamp
from enemy import CyberCar


def _lerp(lo, hi, t):
    return lo + (hi - lo) * clamp(t, 0.0, 1.0)


class ModeManager:
    """Interface comum. Um ModeManager NÃO herda de WaveManager nem o substitui — ele só pilota
    game.wave (e eventualmente cria objetos avulsos) a cada quadro."""
    mode_key = None

    def __init__(self, game):
        self.game = game
        self.wave = game.wave          # mesmo WaveManager de sempre: collisions.py/player.py dependem dele
        self.elapsed = 0.0
        self.ended = False
        self.reset()

    def reset(self):
        """Prepara o estado inicial do modo. Chamado uma vez, em __init__."""
        raise NotImplementedError

    def update(self, dt):
        raise NotImplementedError

    def hud_lines(self):
        """[(texto, cor)] curto para o HUD — mesmo contrato de HazardManager.hud_lines()."""
        return []

    def result_lines(self):
        """[(rótulo, valor)] para a tela de game over (ver game.py _draw_gameover)."""
        return []

    @property
    def record_value(self):
        """Valor numérico deste resultado no campo usado por settings.RECORD_FIELD[mode_key]."""
        raise NotImplementedError

    def on_match_end(self):
        """Chamado uma vez por Game.end_match() quando a partida deste modo termina: devolve
        (is_new_record, record_value) já GRAVANDO o recorde no config (nunca piora um recorde)."""
        value = self.record_value
        is_new = self.game.config.set_record(self.mode_key, value)
        return is_new, self.game.config.get_record(self.mode_key)


# ======================================================================= ROCKETS SKY
class RocketsSkyMode(ModeManager):
    """Sobrevivência por TEMPO: chuva de foguetes cada vez mais intensa. Reaproveita 100% da classe
    Rocket e da fase 'rockets' do HazardManager — só pilota hazards.phase_cfg a cada quadro conforme
    o nível sobe, e nunca deixa a fase terminar (duration enorme; ver _ensure_phase_running)."""
    mode_key = "rockets_sky"

    def reset(self):
        g = self.game
        wv = self.wave
        # O estado "mode" existe só para os ModeManagers (ver WaveManager.update): roda hazards.update(dt)
        # a cada quadro, sem NUNCA reagir a hazards.sequence_done chamando _finish_round() por conta
        # própria — quem decide o que fazer quando uma fase termina é este ModeManager.
        wv.round_no = 0
        wv.state = "mode"
        wv.squads, wv.enemies, wv.solos, wv.cars = [], [], [], []
        hz = wv.hazards
        hz.reset()
        self.level = 1
        self._apply_level_cfg()
        # Entra direto na fase "rockets", usando os mesmos stage/phase do HazardManager clássico para
        # herdar toda a lógica de spawn/física/colisão/explosão sem duplicar nada.
        hz.plan = dict(scale=1.0, saws=0, order=(), cfg={"rockets": self.phase_cfg})
        hz.phase = "rockets"
        hz.phase_cfg = self.phase_cfg
        hz.sequence_active = True
        hz.sequence_done = False
        hz.stage = "run"
        hz.stage_t = 0.0
        hz.phase_t = 0.0
        hz.run_t = 0.0
        hz.spawn_t = S.ROCKETS_SKY_FIRST_DELAY
        g.show_banner("ROCKETS SKY", "SOBREVIVA O MÁXIMO QUE PUDER!", "#ff7a1a", 2.0, alert=True)
        g.audio.on_boss_warning()

    def _level_t(self):
        """0..1: progresso suave até o nível de softcap (daí em diante, dificuldade praticamente no teto)."""
        return (self.level - 1) / max(1, S.ROCKETS_SKY_LEVEL_SOFTCAP - 1)

    def _mix_for_level(self):
        mix = S.ROCKETS_SKY_MIX_BY_LEVEL[0][1]
        for min_level, m in S.ROCKETS_SKY_MIX_BY_LEVEL:
            if self.level >= min_level:
                mix = m
        return mix

    def _apply_level_cfg(self):
        t = self._level_t()
        lo_i, hi_i = S.ROCKETS_SKY_INTERVAL
        self.phase_cfg = dict(
            duration=1e9,          # nunca "acaba sozinha": a fase roda até o jogo terminar
            max_alive=int(round(_lerp(S.ROCKETS_SKY_MAX_ALIVE[0], S.ROCKETS_SKY_MAX_ALIVE[1], t))),
            interval=(_lerp(lo_i[0], hi_i[0], t), _lerp(lo_i[1], hi_i[1], t)),
            mix=self._mix_for_level(),
            speed_mult=_lerp(S.ROCKETS_SKY_SPEED_MULT[0], S.ROCKETS_SKY_SPEED_MULT[1], t),
        )
        # hazards.py lê hz.phase_cfg a cada spawn/quadro (_run_rockets/_spawn_rocket): atualizar aqui
        # já é o suficiente para a dificuldade subir em tempo real, sem reiniciar a fase.
        self.wave.hazards.phase_cfg = self.phase_cfg

    def update(self, dt):
        if self.ended:
            return
        self.elapsed += dt
        new_level = 1 + int(self.elapsed // S.ROCKETS_SKY_LEVEL_INTERVAL)
        if new_level != self.level:
            self.level = new_level
            self._apply_level_cfg()
            self.game.flash("#ff7a1a", 0.12)
            self.game.fx.popup(S.WIDTH // 2, S.HUD_H + 90, f"NÍVEL {self.level}", "#ff7a1a", 24)
        # A fase "rockets" do HazardManager já cuida de spawn/física/colisão/explosão sozinha a partir
        # daqui (hz.update(dt) é chamado por WaveManager.update, que o Game já chama todo quadro).
        # HAZARD_PHASE_TIMEOUT é uma trava "anti-impasse" pensada para uma fase finita (combate clássico);
        # aqui a fase é deliberadamente infinita, então phase_t é mantido sempre abaixo do teto.
        hz = self.wave.hazards
        if hz.phase_t > S.HAZARD_PHASE_TIMEOUT * 0.5:
            hz.phase_t = 0.0

    @staticmethod
    def _mmss(seconds):
        mins, secs = divmod(int(seconds), 60)
        return f"{mins:02d}:{secs:02d}"

    def hud_lines(self):
        # Formato pedido no design doc (seção 14), adaptado ao idioma/estilo do HUD: MODO / TEMPO / NÍVEL.
        return [(f"TEMPO {self._mmss(self.elapsed)}", (255, 255, 255)),
                (f"NÍVEL {self.level}", S.hx("#ff7a1a"))]

    def result_lines(self):
        # Formato da tela de game over (seção 21): TEMPO DE SOBREVIVÊNCIA / NÍVEL DO FOGUETE / MELHOR TEMPO.
        best = self.game.config.get_record("rockets_sky")
        return [("TEMPO DE SOBREVIVÊNCIA", self._mmss(self.elapsed)),
                ("NÍVEL DO FOGUETE", str(self.level)),
                ("MELHOR TEMPO", self._mmss(max(best, self.elapsed)))]

    @property
    def record_value(self):
        return self.elapsed


# ======================================================================= BALL RAIN
class BallRainMode(ModeManager):
    """Sobrevivência por ROUND: cada round libera uma onda de Ball Pods (+ Bouncing Spheres a partir de
    BALL_RAIN_SPHERES_START_ROUND), cada vez maior e mais rápida. Reaproveita 100% a máquina de estados
    de fases do HazardManager (warn -> run -> cleared -> próxima fase), a mesma usada pelo Clássico —
    só reabastece hz.order/hz.plan quando uma rodada termina (hz.sequence_done), em vez de fechar o
    round de verdade (WaveManager.begin_round nunca é chamado neste modo)."""
    mode_key = "ball_rain"

    def reset(self):
        g, wv = self.game, self.wave
        wv.round_no = 0
        wv.state = "mode"
        wv.squads, wv.enemies, wv.solos, wv.cars = [], [], [], []
        wv.hazards.reset()
        self.round_no = 0
        self.destroyed = 0           # cápsulas + esferas destruídas na partida inteira (não usado no recorde,
        # mas compõe um placar informativo futuro; result_lines() só expõe o round alcançado, como pedido)
        self._begin_round(1)
        g.show_banner("BALL RAIN", "SOBREVIVA ÀS CÁPSULAS E ESFERAS!", "#37c8ff", 2.0, alert=True)
        g.audio.on_boss_warning()

    def _counts_for_round(self, n):
        pods = min(S.BALL_RAIN_MAX_PODS, S.BALL_RAIN_INITIAL_PODS + S.BALL_RAIN_POD_INCREMENT * (n - 1))
        spheres = 0
        if n >= S.BALL_RAIN_SPHERES_START_ROUND:
            k = n - S.BALL_RAIN_SPHERES_START_ROUND
            spheres = min(S.BALL_RAIN_MAX_SPHERES, S.BALL_RAIN_INITIAL_SPHERES + S.BALL_RAIN_SPHERE_INCREMENT * k)
        return pods, spheres

    def _speed_mult_for_round(self, n):
        return min(S.BALL_RAIN_MAX_SPEED_MULT, 1.0 + S.BALL_RAIN_SPEED_GROWTH_PER_ROUND * (n - 1))

    def _stagger_for_round(self, n):
        lo, hi = S.BALL_RAIN_STAGGER
        # quanto maior o round, menor o intervalo entre nascimentos (até o teto "hi")
        t = clamp((n - 1) / 12.0, 0.0, 1.0)
        return _lerp(lo, hi, t)

    def _begin_round(self, n):
        """Monta a 'rodada' n (ball_pod, e spheres quando aplicável) e entra na máquina de fases do
        HazardManager exatamente como plan_for()/begin_sequence() fariam no Clássico."""
        self.round_no = n
        hz = self.wave.hazards
        pods, spheres = self._counts_for_round(n)
        speed_mult = self._speed_mult_for_round(n)
        stagger = self._stagger_for_round(n)
        cfg = {
            "ball_pod": dict(pods=self._pod_mix(n, pods), stagger=stagger, speed_mult=speed_mult),
        }
        order = ["ball_pod"]
        if spheres > 0:
            cfg["spheres"] = dict(mix=self._sphere_mix(n, spheres), stagger=stagger, speed_mult=speed_mult)
            order.append("spheres")
        hz.plan = dict(scale=1.0, saws=0, order=tuple(order), cfg=cfg)
        hz.order = list(order)
        hz.sequence_active, hz.sequence_done = True, False
        hz._start_warn(hz.order.pop(0))

    @staticmethod
    def _pod_mix(n, count):
        # cápsulas "bounce" (ricocheteantes) entram a partir do round 2, numa fração crescente da onda.
        if n < 2:
            return ("release",) * count
        bounce_n = min(count, max(1, count // 2))
        mix = ["bounce"] * bounce_n + ["release"] * (count - bounce_n)
        random.shuffle(mix)
        return tuple(mix)

    @staticmethod
    def _sphere_mix(n, count):
        heavy_n = min(count, count // 3)
        return (("heavy", heavy_n), ("light", count - heavy_n)) if heavy_n > 0 else (("light", count),)

    def update(self, dt):
        if self.ended:
            return
        self.elapsed += dt
        hz = self.wave.hazards
        if hz.sequence_done:
            # a rodada acabou (todas as fases dela resolvidas): começa a próxima, mais difícil.
            self.game.show_banner(f"ROUND {self.round_no + 1}", "Preparar nova chuva...", "#46f08a", 1.4)
            self._begin_round(self.round_no + 1)

    def hud_lines(self):
        return [(f"ROUND {self.round_no}", S.hx("#37c8ff"))] + self.wave.hazards.hud_lines()

    def result_lines(self):
        best = self.game.config.get_record("ball_rain")
        return [("ROUND ALCANÇADO", str(self.round_no)),
                ("MELHOR ROUND", str(max(best, self.round_no)))]

    @property
    def record_value(self):
        return self.round_no


# ======================================================================= MECHANIC ROOM
class MechanicRoomMode(ModeManager):
    """Sobrevivência por CICLO: cada ciclo tem +1 cápsula ricocheteante (BallPod variante 'bounce') que
    o anterior, e cada vez mais rápida/intensa, sem teto de quantidade (design doc 7.2). Usa a mesma
    fase 'ball_pod' do HazardManager, só com pods=('bounce',)*N — nunca a variante 'release'."""
    mode_key = "mechanic_room"

    def reset(self):
        g, wv = self.game, self.wave
        wv.round_no = 0
        wv.state = "mode"
        wv.squads, wv.enemies, wv.solos, wv.cars = [], [], [], []
        wv.hazards.reset()
        self.wave_no = 0
        self._begin_wave(1)
        g.show_banner("MECHANIC ROOM", "DESTRUA TODAS AS CÁPSULAS!", "#ff9a3c", 2.0, alert=True)
        g.audio.on_boss_warning()

    def _pods_for_wave(self, n):
        return S.MECHANIC_ROOM_INITIAL_PODS + S.MECHANIC_ROOM_POD_INCREMENT * (n - 1)

    def _speed_mult_for_wave(self, n):
        return min(S.MECHANIC_ROOM_MAX_SPEED_MULT, 1.0 + S.MECHANIC_ROOM_SPEED_INCREMENT * (n - 1))

    def _bounce_mult_for_wave(self, n):
        return min(S.MECHANIC_ROOM_MAX_BOUNCE_MULT, 1.0 + S.MECHANIC_ROOM_BOUNCE_INCREMENT * (n - 1))

    def _begin_wave(self, n):
        self.wave_no = n
        hz = self.wave.hazards
        count = min(S.MECHANIC_ROOM_MAX_ACTIVE, self._pods_for_wave(n))
        cfg = dict(pods=("bounce",) * count, stagger=0.35,
                    speed_mult=self._speed_mult_for_wave(n), bounce_mult=self._bounce_mult_for_wave(n))
        hz.plan = dict(scale=1.0, saws=0, order=("ball_pod",), cfg={"ball_pod": cfg})
        hz.order = ["ball_pod"]
        hz.sequence_active, hz.sequence_done = True, False
        hz._start_warn(hz.order.pop(0))

    def update(self, dt):
        if self.ended:
            return
        self.elapsed += dt
        hz = self.wave.hazards
        if hz.sequence_done:
            next_n = self.wave_no + 1
            self.game.show_banner(f"WAVE {next_n}", "Mais cápsulas, mais rápidas...", "#ff9a3c", 1.3)
            self._begin_wave(next_n)

    @staticmethod
    def _mmss(seconds):
        mins, secs = divmod(int(seconds), 60)
        return f"{mins:02d}:{secs:02d}"

    def hud_lines(self):
        # Formato exato do design doc (seção 7.5): WAVE / SPHERES / NEXT / TIME.
        current = self._pods_for_wave(self.wave_no)
        nxt = self._pods_for_wave(self.wave_no + 1)
        return [(f"WAVE {self.wave_no}", S.hx("#ff9a3c")),
                (f"CÁPSULAS {current}  PRÓXIMA {nxt}", (255, 255, 255)),
                (f"TEMPO {self._mmss(self.elapsed)}", (200, 210, 220))]

    def result_lines(self):
        # Seção 7.6: maior nível alcançado, tempo sobrevivido, quantidade total de esferas destruídas
        # (contagem real, por jogador, já mantida em Player.kills_by_type — nunca duplicada aqui).
        best = self.game.config.get_record("mechanic_room")
        destroyed = sum(p.kills_by_type.get("pod", 0) for p in self.game.players)
        return [("MAIOR WAVE ALCANÇADA", str(self.wave_no)),
                ("TEMPO SOBREVIVIDO", self._mmss(self.elapsed)),
                ("CÁPSULAS DESTRUÍDAS", str(destroyed)),
                ("MELHOR WAVE", str(max(best, self.wave_no)))]

    @property
    def record_value(self):
        return self.wave_no


# ======================================================================= CRAZY CAR
class CrazyCarMode(ModeManager):
    """Sobrevivência por NÍVEL DO CARRO: o CyberCar (mesma classe do Clássico/50 Rounds, nunca uma
    cópia) volta mais forte a cada derrota — mais vida, mais velocidade, turbo mais cedo/frequente e,
    a partir de um certo nível, foguetes extras (reaproveitando a classe Rocket e a fase 'rockets' do
    HazardManager, como no Rockets Sky). O carro em si NÃO usa o HazardManager: ele é um Enemy comum,
    gerido por wave.enemies/solos/cars — exatamente como no Clássico — com phasing sempre ativo."""
    mode_key = "crazy_car"

    def reset(self):
        g, wv = self.game, self.wave
        wv.round_no = 0
        wv.state = "mode"
        wv.squads, wv.enemies, wv.solos, wv.cars = [], [], [], []
        wv.hazards.reset()
        self.level = 1
        self.defeats = 0            # "CAR DEFEATS" (seção 21): quantas vezes o carro já foi derrotado
        self.car = None
        self._spawn_car()
        g.show_banner("CRAZY CAR", "DERROTE O CARRO!", "#ff4d6d", 2.0, alert=True)
        g.audio.on_boss_warning()

    # ------------------------------------------------------------ progressão (seções 8.4 a 8.7)
    @staticmethod
    def _impacts_for_level(level):
        tbl = S.CRAZY_CAR_IMPACTS_BY_LEVEL
        if level <= len(tbl):
            base = tbl[level - 1]
        else:
            base = tbl[-1] + S.CRAZY_CAR_IMPACTS_GROWTH * (level - len(tbl))
        return min(S.CRAZY_CAR_MAX_IMPACTS, base)

    @staticmethod
    def _speed_for_level(level):
        return min(S.CRAZY_CAR_MAX_SPEED, S.CAR["speed"] + S.CRAZY_CAR_SPEED_INCREMENT * (level - 1))

    @staticmethod
    def _turbo_for_level(level):
        """(usa_turbo, chance_extra) — nível < START: sem turbo (8.6: 'Level 1-4 → sem turbo')."""
        if level < S.CRAZY_CAR_TURBO_START_LEVEL:
            return False, 0.0
        chance = min(S.CRAZY_CAR_TURBO_CHANCE_MAX,
                     S.CRAZY_CAR_TURBO_CHANCE_BY_LEVEL * (level - S.CRAZY_CAR_TURBO_START_LEVEL + 1))
        return True, chance

    @staticmethod
    def _rockets_for_level(level):
        """None quando o nível ainda não libera foguetes (8.7: 'Level 1-3 → Somente Crazy Car')."""
        if level < S.CRAZY_CAR_ROCKETS_START_LEVEL:
            return None
        above = level - S.CRAZY_CAR_ROCKETS_START_LEVEL
        max_alive = min(S.CRAZY_CAR_ROCKETS_MAX_ALIVE_CAP, 1 + S.CRAZY_CAR_ROCKETS_MAX_ALIVE_BY_LEVEL * above)
        lo, hi = S.CRAZY_CAR_ROCKETS_INTERVAL
        interval = (max(hi, lo - 0.3 * above), max(hi, lo - 0.3 * above) + 0.4)
        mix = (("small", 5),) if level < S.CRAZY_CAR_ROCKETS_LARGE_LEVEL else (("small", 3), ("medium", 2))
        return dict(duration=1e9, max_alive=max_alive, interval=interval, mix=mix, speed_mult=1.0)

    # ------------------------------------------------------------ spawn / progressão de nível
    def _spawn_car(self):
        """Cria o carro do nível atual sempre na borda direita (CyberCar.spawn_x(), seção 8.9) — mesma
        regra do Clássico/50 Rounds, nunca uma posição própria deste modo."""
        wv = self.wave
        impacts = self._impacts_for_level(self.level)
        speed = self._speed_for_level(self.level)
        turbo, _ = self._turbo_for_level(self.level)
        car = CyberCar(wv, speed=speed, turbo=turbo, impacts=impacts)
        car.phasing_enabled = True     # seção 8.3: phasing sempre ativo neste modo, em qualquer nível
        wv.enemies.append(car)
        wv.solos.append(car)
        wv.cars.append(car)
        self.car = car
        self._apply_rocket_phase()

    def _apply_rocket_phase(self):
        """Liga/atualiza a fase 'rockets' do HazardManager conforme o nível (8.7); reaproveita 100% a
        classe Rocket, exatamente como RocketsSkyMode — nunca duplica física de foguete."""
        hz = self.wave.hazards
        cfg = self._rockets_for_level(self.level)
        if cfg is None:
            hz.sequence_active = False     # ainda sem foguetes neste nível: hazards.update(dt) não faz nada
            hz.phase = None
            return
        hz.phase_cfg = cfg
        if hz.phase != "rockets":
            hz.plan = dict(scale=1.0, saws=0, order=(), cfg={"rockets": cfg})
            hz.phase = "rockets"
            hz.sequence_active = True
            hz.sequence_done = False
            hz.stage = "run"
            hz.stage_t = 0.0
            hz.phase_t = 0.0
            hz.run_t = 0.0
            hz.spawn_t = S.ROCKETS_SKY_FIRST_DELAY

    def update(self, dt):
        if self.ended:
            return
        self.elapsed += dt
        # wave.state == "mode" não atualiza wave.solos sozinho (diferente de "active" no Clássico), então
        # o carro — um Enemy comum, gerido por wave.enemies/solos/cars como de costume — precisa ser
        # avançado aqui; collisions.py (stomp/contato) continua lendo-o de wave.cars normalmente.
        if self.car is not None and self.car.alive:
            self.car.update(dt)
        hz = self.wave.hazards
        if hz.sequence_active and hz.phase_t > S.HAZARD_PHASE_TIMEOUT * 0.5:  # mitigação: fase infinita
            hz.phase_t = 0.0
        hz.update(dt)       # sempre chamado: atualiza foguetes existentes mesmo quando sequence_active é False
        if self.car is not None and not self.car.alive:
            self._on_car_defeated()

    def _on_car_defeated(self):
        g = self.game
        self.defeats += 1
        self.level += 1
        g.show_banner("CAR DEFEATED!", f"NÍVEL {self.level}", "#ff4d6d", 1.6, alert=True)
        self._spawn_car()

    def hud_lines(self):
        # Formato exato do design doc (seção 14): MODE / CAR LEVEL / CAR HP.
        hp = int(self.car.impacts_left) if self.car is not None and self.car.alive else 0
        return [(f"NÍVEL {self.level}", S.hx("#ff4d6d")), (f"VIDA DO CARRO {hp}", (255, 255, 255))]

    def result_lines(self):
        # Seção 21: CAR LEVEL / CAR DEFEATS / BEST LEVEL.
        best = self.game.config.get_record("crazy_car")
        return [("NÍVEL DO CARRO", str(self.level)),
                ("CARROS DERROTADOS", str(self.defeats)),
                ("MELHOR NÍVEL", str(max(best, self.level)))]

    @property
    def record_value(self):
        return self.level


# ======================================================================= fábrica
MODE_CLASSES = {
    "rockets_sky": RocketsSkyMode,
    "ball_rain": BallRainMode,
    "mechanic_room": MechanicRoomMode,
    "crazy_car": CrazyCarMode,
}


def make_mode_runner(game_mode, game):
    """Cria o ModeManager certo para `game_mode` (uma das settings.SURVIVAL_GAME_MODES)."""
    cls = MODE_CLASSES[game_mode]
    return cls(game)
