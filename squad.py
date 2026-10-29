"""
squad.py — Squad (formação: grupo de inimigos do mesmo tipo que se move como
um bloco, inverte nas bordas e desce) e SpatialGrid (grade uniforme usada
pelo CollisionManager para a fase ampla de tiro×alvo). Porte fiel do
main.py original.
"""
import random

import settings as S


class Squad:
    def __init__(self, wave, kind, direction):
        self.wave = wave
        self.kind = kind
        self.members = []
        self.dir = direction
        self.descent_scale = 1.0
        self.base_speed = S.ENEMY_TYPES[kind]["speed"] * wave.speed_factor * wave.diff_speed
        self.speed_mult = self.target_mult = 1.0
        self.pattern_t = random.uniform(0.8, 1.8)
        self.mode = "cruise"
        self.descend_left = 0.0
        self.entering = True

    def remove(self, e):
        if e in self.members:
            self.members.remove(e)

    def _pattern(self, dt):
        self.pattern_t -= dt
        if self.kind == "ship":
            if self.pattern_t <= 0:
                self.pattern_t = random.uniform(1.2, 2.6)
                self.target_mult = random.uniform(0.7, 1.45)
                if random.random() < 0.15:
                    self.dir *= -1
            self.speed_mult += (self.target_mult - self.speed_mult) * min(1.0, 3 * dt)
        elif self.kind == "machine":
            if self.mode == "cruise" and self.pattern_t <= 0:
                self.mode, self.pattern_t = "burst", 0.8
            elif self.mode == "burst" and self.pattern_t <= 0:
                self.mode, self.pattern_t = "recover", 1.0
            elif self.mode == "recover" and self.pattern_t <= 0:
                self.mode, self.pattern_t = "cruise", random.uniform(3.5, 5.5)
            self.target_mult = {"cruise": 1.0, "burst": 2.3, "recover": 0.3}[self.mode]
            self.speed_mult += (self.target_mult - self.speed_mult) * min(1.0, 8 * dt)

    def update(self, dt):
        ms = self.members
        if not ms:
            return
        if self.entering:
            done = True
            for e in ms:
                e.entry = max(0.0, e.entry - (e.entry * 5.0 + 40.0) * dt)
                if e.entry > 0.5:
                    done = False
            if done:
                self.entering = False
                for e in ms:
                    e.entry = 0.0
        else:
            self._pattern(dt)
            dx = self.dir * self.base_speed * self.speed_mult * self.wave.game.enemy_move_mult * dt
            for e in ms:
                e.slot_x += dx
            left = min(e.slot_x - e.w / 2 for e in ms)
            right = max(e.slot_x + e.w / 2 for e in ms)
            if self.dir > 0 and right >= S.WIDTH - S.EDGE_MARGIN:
                fix = (S.WIDTH - S.EDGE_MARGIN) - right
                for e in ms:
                    e.slot_x += fix
                self.dir = -1
                self.descend_left += S.DESCENT_STEP * self.descent_scale
            elif self.dir < 0 and left <= S.EDGE_MARGIN:
                fix = S.EDGE_MARGIN - left
                for e in ms:
                    e.slot_x += fix
                self.dir = 1
                self.descend_left += S.DESCENT_STEP * self.descent_scale
            if self.descend_left > 0:
                step = min(self.descend_left, S.DESCENT_SPEED * dt)
                self.descend_left -= step
                for e in ms:
                    e.slot_y = min(e.slot_y + step, S.GROUND_Y - e.h / 2)
        for e in ms:
            e.update(dt)


class SpatialGrid:
    """Grade uniforme para a colisão tiro x alvos: cada tiro só consulta as
    células que toca. Objetos precisam ter o atributo 'hb' = (x1, y1, x2, y2)."""

    def __init__(self, cell=S.GRID_CELL):
        self.cell = cell
        self.cells = {}

    def rebuild(self, objs):
        cells, c = {}, self.cell
        for o in objs:
            x1, y1, x2, y2 = o.hb
            for gx in range(int(x1 // c), int(x2 // c) + 1):
                for gy in range(int(y1 // c), int(y2 // c) + 1):
                    cells.setdefault((gx, gy), []).append(o)
        self.cells = cells

    def query(self, rect):
        c, cells = self.cell, self.cells
        x1, y1, x2, y2 = rect
        out = None
        for gx in range(int(x1 // c), int(x2 // c) + 1):
            for gy in range(int(y1 // c), int(y2 // c) + 1):
                lst = cells.get((gx, gy))
                if lst:
                    if out is None:
                        out = list(lst)
                    else:
                        out.extend(o for o in lst if o not in out)
        return out or ()
