"""
wave.py — WaveManager: progressão dos 10 rounds, composição das formações,
encontros especiais (chefes, carro, jatos) e ataques de bomba dos inimigos
padrão. Porte fiel do main.py original; a única mudança é que os inimigos
não precisam mais de build(gfx) — em Pygame eles só se desenham a cada
quadro via draw(surf), então a criação é só "adicionar à lista".
"""
import math
import random

import settings as S
from enemy import ENEMY_CLASSES, Miniboss, Mothership, FinalBoss, CyberCar, Jet, MiniShip
from squad import Squad
from utils import clamp


def wave_counts(round_no):
    """Quantidade de (drones, naves, máquinas) PADRÃO do round (1 a 10, depois modo infinito)."""
    if round_no in S.ROUND_TABLE:
        base = S.ROUND_TABLE[round_no]
    else:
        n = round_no - S.ENDLESS_BASE_ROUND
        base = tuple(min(cap, b + g * n) for b, g, cap in
                     zip(S.ROUND_TABLE[S.ENDLESS_BASE_ROUND], S.GROWTH_PER_ROUND, S.MAX_COUNTS))
    return dict(zip(S.COUNT_ORDER, base))


class WaveManager:
    def __init__(self, game):
        self.game = game
        self.reset()

    def reset(self):
        self.round_no = 0
        self.state = "idle"            # idle | intro | active | clear
        self.timer = 0.0
        self.squads, self.enemies = [], []
        self.solos, self.cars = [], []
        self.planned = 0
        self.bomb_timer = 0.0
        self.speed_factor = 1.0
        self.diff_speed = 1.0
        self.special = None

    def remaining(self):
        if self.state == "intro":
            return self.planned
        return len(self.enemies)

    def boss(self):
        for e in self.enemies:
            if e.is_boss:
                return e
        return None

    @staticmethod
    def special_count(sp):
        return S.JET["count"] if sp and sp["kind"] == "jets" else (1 if sp else 0)

    def scaled_hp(self, base):
        return max(1, int(round(base * self.game.diff["enemy_hp"])))

    # ------------------------------------------------------------ rounds
    def begin_round(self, n):
        self.round_no = n
        self.state = "intro"
        self.squads, self.enemies = [], []
        self.solos, self.cars = [], []
        sp = S.ROUND_SPECIALS.get(n)
        self.special = sp
        self.timer = sp["intro"] if sp else S.ROUND_INTRO_TIME
        self.planned = sum(wave_counts(n).values()) + self.special_count(sp)
        self.game.drops_this_round = 0
        if sp:
            self.game.show_banner("ROUND %d" % n, sp["title"], "#ff4d6d", self.timer, alert=True)
            self.game.flash("#ff2a4d", 0.25)
            self.game.audio.on_boss_warning()
        else:
            self.game.show_banner("ROUND %d" % n, S.ROUND_NOTES.get(n, S.DEFAULT_NOTE), "#ffe14d", self.timer)

    def spawn_wave(self):
        g = self.game
        n = self.round_no
        sp = self.special
        self.speed_factor = min(S.MAX_SPEED_FACTOR, 1.0 + S.SPEED_GROWTH_PER_ROUND * (n - 1))
        self.diff_speed = g.diff["enemy_speed"]
        counts = wave_counts(n)
        y_cursor = sp["formation_y"] if sp and sp.get("formation_y") else S.HUD_H + 16
        for kind in S.ENEMY_ORDER:
            total = counts[kind]
            if total <= 0:
                continue
            cfg = S.ENEMY_TYPES[kind]
            rows = math.ceil(total / cfg["per_row"])
            per = math.ceil(total / rows)
            squad = Squad(self, kind, random.choice((-1, 1)))
            if sp:
                squad.descent_scale = sp["descent_scale"]
            hp = self.scaled_hp(cfg["hp"] + int(cfg["hp_growth"] * (n - 1)))
            left = total
            for r in range(rows):
                cnt = min(per, left)
                left -= cnt
                row_y = y_cursor + cfg["pitch_y"] * (r + 0.5)
                x0 = S.WIDTH / 2 - (cnt - 1) * cfg["pitch_x"] / 2
                for i in range(cnt):
                    e = ENEMY_CLASSES[kind](squad, kind, x0 + i * cfg["pitch_x"], row_y, hp,
                                             random.uniform(0, math.tau))
                    squad.members.append(e)
                    self.enemies.append(e)
            y_cursor += rows * cfg["pitch_y"]
            self.squads.append(squad)
        if sp:
            self.spawn_special(sp)
        self.planned = len(self.enemies)

    # ------------------------------------------------------------ encontros especiais
    def _add_solo(self, e):
        self.enemies.append(e)
        self.solos.append(e)
        return e

    def spawn_special(self, sp):
        g, n, k = self.game, self.round_no, sp["kind"]
        sc = self.scaled_hp
        if k == "miniboss":
            self._add_solo(Miniboss(self, S.WIDTH / 2, sc(S.ENEMY_TYPES["miniboss"]["hp"])))
        elif k == "mothership":
            self._add_solo(Mothership(self, S.WIDTH / 2, sc(S.ENEMY_TYPES["mothership"]["hp"])))
        elif k == "finalboss":
            self._add_solo(FinalBoss(self, S.WIDTH / 2, sc(S.ENEMY_TYPES["finalboss"]["hp"])))
        elif k == "car":
            car = CyberCar(self, S.WIDTH / 2, S.CAR["speed"] * sp.get("speed_mult", 1.0) * self.diff_speed,
                            turbo=sp.get("turbo", False))
            self._add_solo(car)
            self.cars.append(car)
        elif k == "jets":
            cfg = S.ENEMY_TYPES["jet"]
            hp = sc(cfg["hp"] + int(cfg["hp_growth"] * (n - 1)))
            for i in range(S.JET["count"]):
                self._add_solo(Jet(self, hp, random.uniform(*S.JET["first_delay"]) + 1.3 * i,
                                    S.JET["lanes"][i % len(S.JET["lanes"])]))
        if k in ("miniboss", "mothership", "finalboss"):
            g.shake(0.5, 8)

    def spawn_minis(self, n, x, y):
        """Naves menores geradas pela nave-mãe: entram de fato na lista de inimigos."""
        hp = self.scaled_hp(S.ENEMY_TYPES["mini"]["hp"])
        squad = Squad(self, "mini", random.choice((-1, 1)))
        squad.entering = False
        for i in range(n):
            e = MiniShip(squad, "mini", clamp(x + (i - (n - 1) / 2) * 66, 60, S.WIDTH - 60),
                          clamp(y + 20, 110, 320), hp, random.uniform(0, math.tau))
            e.entry = 0.0
            e.update(0.0)
            squad.members.append(e)
            self.enemies.append(e)
        self.squads.append(squad)

    # ------------------------------------------------------------ manutenção
    def remove_enemy(self, e):
        e.alive = False
        if e in self.enemies:
            self.enemies.remove(e)
        if e.solo and e in self.solos:
            self.solos.remove(e)
        if e in self.cars:
            self.cars.remove(e)
        if e.squad is not None:
            e.squad.remove(e)

    def bomb_interval(self):
        return max(S.BOMB_INTERVAL_MIN, S.BOMB_INTERVAL_BASE - S.BOMB_INTERVAL_DECAY * (self.round_no - 1))

    def drop_bomb(self):
        shooters = ("ship", "machine") + (("drone",) if self.round_no >= S.DRONE_BOMB_ROUND else ())
        cands = [e for e in self.enemies if e.alive and not e.solo and not e.squad.entering and e.kind in shooters]
        if not cands:
            return
        e = random.choice(cands)
        speed = S.BOMB_SPEED + S.BOMB_SPEED_GROWTH * (self.round_no - 1)
        for ox in ((-22, 22) if e.kind == "machine" else (0,)):
            self.game.spawn_hostile("bomb", e.x + ox, e.y + e.h / 2, vy=speed)

    def update(self, dt):
        g = self.game
        if self.state == "intro":
            self.timer -= dt
            if self.timer <= 0:
                self.spawn_wave()
                self.state = "active"
                self.bomb_timer = S.BOMB_FIRST_DELAY
        elif self.state == "active":
            for sq in self.squads:
                sq.update(dt)
            for e in self.solos:
                e.update(dt)
            self.squads = [s for s in self.squads if s.members]
            if self.round_no >= 2:
                self.bomb_timer -= dt * g.enemy_attack_rate
                if self.bomb_timer <= 0:
                    self.drop_bomb()
                    self.bomb_timer = self.bomb_interval()
            if not self.enemies:
                self.state = "clear"
                self.timer = S.ROUND_CLEAR_TIME
                g.on_round_cleared(self.round_no)
        elif self.state == "clear":
            self.timer -= dt
            if self.timer <= 0:
                if self.game.rounds_to_win and self.round_no >= self.game.rounds_to_win:
                    g.end_match(True)
                else:
                    self.begin_round(self.round_no + 1)

    def draw(self, surf):
        for e in self.enemies:
            e.draw(surf)
