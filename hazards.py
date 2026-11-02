"""
hazards.py — perigos ambientais do ORBITAL HEADS.

Quatro hazards, todos com hitbox, colisão e comportamento próprios. Todos os números vêm de
settings.py (HAZARD_ROUNDS, ROCKET_TYPES, BALL_POD_TYPES, POD_BALL, SPHERE_TYPES, BLACK_SAW, ...).

  * BlackSaw        — disco que circula o PERÍMETRO da arena. Nasce junto do combate e fica ativa durante
                      o combate e TODAS as fases extras; nunca bloqueia a conclusão do round.
  * Rocket          — chuva de foguetes (3 tamanhos). Fase temporizada, DEPOIS do combate.
  * BallPod         — cápsula "release" (desce, abre, libera mini-esferas) ou "bounce" (fechada, ricocheteia).
                      Fase DEPOIS do combate; só termina quando cápsulas e mini-esferas obrigatórias acabam.
  * BouncingSphere  — esferas com gravidade e quique (leve/pesada). Fase DEPOIS do combate; só termina
                      quando todas forem destruídas. (Também é usada para as mini-esferas das cápsulas.)

HazardManager guarda as listas de objetos vivos e a MÁQUINA DE FASES de um round:

    combate (WaveManager "active") ──inimigos zerados──► "hazard" ──► [warn → run → (resolve) → cleared]*  ──► clear
                                                                       uma vez por fase configurada em order

As movimentações usam o dt recebido (WaveManager.update só roda com o jogo em "playing", então a pausa
congela temporizadores e movimento sem nenhum tratamento extra). Colisões jogador×hazard, tiro×hazard e
hazard×arena ficam em collisions.py; este módulo só move, desenha e decide quando cada fase acaba.
"""
import math
import random

import pygame

import settings as S
from utils import clamp, draw_glow_circle, pulse, circle_hits_rect, overlap

ARENA_L, ARENA_R = 0.0, float(S.WIDTH)
ARENA_T, ARENA_B = float(S.HUD_H), float(S.GROUND_Y)

WHITE = (248, 252, 255)
STEEL = (96, 110, 130)
STEEL_DARK = (34, 42, 58)
OUTLINE = (8, 12, 22)


def _mix(a, b, k):
    return tuple(max(0, min(255, int(a[i] * (1 - k) + b[i] * k))) for i in range(3))


def _rot(lx, ly, c, s, ox, oy):
    """Gira o ponto local (lx, ly) pelo par (cos, sin) e translada para (ox, oy)."""
    return (ox + lx * c + ly * s, oy - lx * s + ly * c)


# ===================================================================== base
class Hazard:
    is_hazard = True
    kind = "hazard"
    mandatory = False      # True: a fase só termina quando todos os mandatórios acabarem
    hurts = True           # dano por contato com o jogador
    points = 0

    def __init__(self, hz):
        self.hz, self.game = hz, hz.game
        self.alive = True
        self.t = 0.0
        self.flash = 0.0
        self.hp = self.max_hp = None
        self.x = self.y = 0.0
        self.r = 10.0
        self.hb = (0.0, 0.0, 0.0, 0.0)
        self.exploded = False

    # --- interface usada por collisions.py / HazardManager
    @property
    def shootable(self):
        return False

    def hitbox(self):
        return self.hb

    def hit(self, dmg):
        """Dano de tiro. Retorna True quando a vida acaba (aí o jogo chama on_destroyed)."""
        if not self.alive or self.hp is None:
            return False
        self.hp -= dmg
        self.flash = 0.08
        if self.hp <= 1e-9:
            self.hp = 0.0
            self.alive = False
            return True
        return False

    def touches(self, hb):
        return False

    def on_player_contact(self, g, p):
        p.take_hit()

    def resolve_arena(self):
        pass

    def update(self, dt, mult):
        self.t += dt
        if self.flash > 0:
            self.flash -= dt

    def fx_pack(self):
        """(tamanho, flash, anel, paleta) da explosão visual deste hazard."""
        col = "#ffd23f"
        return (self.r * 2.2, "#ffffff", col, (col, "#ffffff"))

    def on_destroyed(self, g):
        """Destruído por tiro."""
        size, flash, ring, pal = self.fx_pack()
        g.fx.explosion(self.x, self.y, size, flash, ring, pal)
        g.audio.on_explosion(big=False)

    def force_clear(self, g):
        """Remoção de segurança (fim de fase forçado / limpeza): some com efeito, sem dano."""
        if not self.alive:
            return
        self.alive = False
        size, flash, ring, pal = self.fx_pack()
        g.fx.explosion(self.x, self.y, size * 0.7, flash, ring, pal)

    def _bar(self, surf, w, y_off):
        if self.hp is None or self.max_hp is None or self.max_hp < 3 or self.hp >= self.max_hp:
            return
        ratio = clamp(self.hp / self.max_hp, 0.0, 1.0)
        x0, y0 = self.x - w / 2, self.y + y_off
        col = (70, 240, 138) if ratio > 0.5 else (255, 210, 63) if ratio > 0.25 else (255, 77, 77)
        pygame.draw.rect(surf, (18, 20, 42), (x0, y0, w, 5), border_radius=2)
        pygame.draw.rect(surf, col, (x0 + 1, y0 + 1, (w - 2) * ratio, 3), border_radius=1)


class _Ball(Hazard):
    """Hazard de hitbox circular."""

    def _calc_hb(self):
        return (self.x - self.r, self.y - self.r, self.x + self.r, self.y + self.r)

    def touches(self, hb):
        return circle_hits_rect(self.x, self.y, self.r, hb)


# ===================================================================== ROCKETS
class Rocket(Hazard):
    kind = "rocket"

    def __init__(self, hz, rtype, x, vx, speed):
        super().__init__(hz)
        cfg = self.cfg = S.ROCKET_TYPES[rtype]
        self.rtype = rtype
        self.w, self.h = cfg["w"], cfg["h"]
        self.r = max(self.w, self.h) / 2
        self.x, self.y = x, ARENA_T - self.h / 2          # nasce escondido sob o HUD e desce
        self.vx, self.vy = vx, speed
        self.hp = self.max_hp = float(hz.wave.scaled_hp(cfg["hp"]))
        self.points = cfg["points"]
        self.air_radius, self.ground_radius = cfg["air_radius"], cfg["ground_radius"]
        self.state = "fall"                                # fall -> fuse (no chão, armado) -> detona
        self.fuse = self.fuse_max = cfg["fuse"]
        self.tilt = 0.0
        self.hb = self._calc_hb()

    def _calc_hb(self):
        hw, hh = self.w * 0.5, self.h * 0.5
        return (self.x - hw, self.y - hh, self.x + hw, self.y + hh)

    @property
    def shootable(self):
        return self.state == "fall" and self.hb[3] > S.HUD_H     # só dá para acertar depois que aparece

    def touches(self, hb):
        return self.state == "fall" and overlap(self.hb, hb)

    def on_player_contact(self, g, p):
        g.hazard_blast(self, "air")                           # tocou no jogador: detona (raio pequeno, mas cobre o corpo)

    def update(self, dt, mult):
        super().update(dt, mult)
        if self.state == "fall":
            self.x += self.vx * dt * mult
            self.y += self.vy * dt * mult
            self.tilt = math.atan2(self.vx, self.vy)
        else:
            self.fuse -= dt                                # o pavio no chão corre em tempo real
        self.hb = self._calc_hb()

    def resolve_arena(self):
        if self.state != "fall":
            return
        half = self.w / 2
        if self.x < half:
            self.x, self.vx = half, abs(self.vx)
        elif self.x > ARENA_R - half:
            self.x, self.vx = ARENA_R - half, -abs(self.vx)
        if self.y + self.h / 2 >= ARENA_B:                  # colisão foguete × chão
            self.y = ARENA_B - self.h / 2
            self.state, self.fuse = "fuse", self.fuse_max
            self.vx = self.vy = 0.0
            g = self.game
            g.fx.sparks(self.x, ARENA_B - 2, "#ffd23f", 4)
            g.fx.dust(self.x, ARENA_B, 3)
        self.hb = self._calc_hb()

    def fx_pack(self):
        c = self.cfg
        return (c["size"], *c["fx"])

    def on_destroyed(self, g):
        g.hazard_blast(self, "air")                          # destruído no ar: explosão pequena

    def force_clear(self, g):
        if not self.alive:
            return
        self.alive = self.exploded = False
        size, flash, ring, pal = self.fx_pack()
        g.fx.explosion(self.x, self.y, size * 0.6, flash, ring, pal)

    # --- desenho: casco girado conforme a trajetória (sem criar Surface)
    def draw(self, surf):
        c = self.cfg
        accent = S.hx(c["color"])
        x, y, w, h = self.x, self.y, self.w, self.h
        ang = self.tilt if self.state == "fall" else 0.0
        cs, sn = math.cos(ang), math.sin(ang)

        def P(lx, ly):
            return _rot(lx, ly, cs, sn, x, y)

        blink_white = self.flash > 0 or (self.state == "fuse" and int(self.t * 22) % 2 == 0)
        hull = WHITE if blink_white else (150, 164, 186)
        if self.state == "fall":
            fl = (0.55 + 0.45 * math.sin(self.t * 38)) * h * 0.55
            pygame.draw.polygon(surf, (255, 214, 120), [P(-w * 0.26, -h * 0.46), P(w * 0.26, -h * 0.46), P(0, -h * 0.46 - fl)])
            pygame.draw.polygon(surf, WHITE, [P(-w * 0.12, -h * 0.46), P(w * 0.12, -h * 0.46), P(0, -h * 0.46 - fl * 0.55)])
            draw_glow_circle(surf, x, y, self.r * 1.25, accent, intensity=0.42, layers=2)
        # aletas
        for sd in (-1, 1):
            pygame.draw.polygon(surf, accent, [P(sd * w * 0.38, -h * 0.04), P(sd * w * 0.86, -h * 0.46), P(sd * w * 0.38, -h * 0.36)])
            pygame.draw.polygon(surf, OUTLINE, [P(sd * w * 0.38, -h * 0.04), P(sd * w * 0.86, -h * 0.46), P(sd * w * 0.38, -h * 0.36)], 1)
        # casco + ogiva
        body = [P(-w * 0.40, -h * 0.40), P(w * 0.40, -h * 0.40), P(w * 0.40, h * 0.14), P(0, h * 0.5), P(-w * 0.40, h * 0.14)]
        nozzle = [P(-w * 0.28, -h * 0.40), P(w * 0.28, -h * 0.40), P(w * 0.20, -h * 0.47), P(-w * 0.20, -h * 0.47)]
        pygame.draw.polygon(surf, hull, body)
        pygame.draw.polygon(surf, accent, [P(-w * 0.40, h * 0.14), P(0, h * 0.5), P(w * 0.40, h * 0.14), P(w * 0.26, h * 0.06), P(-w * 0.26, h * 0.06)])
        pygame.draw.polygon(surf, OUTLINE, body, 2)
        pygame.draw.polygon(surf, (52, 60, 78), nozzle)
        pygame.draw.polygon(surf, OUTLINE, nozzle, 1)
        pygame.draw.line(surf, accent, P(-w * 0.40, -h * 0.14), P(w * 0.40, -h * 0.14), 2)
        pygame.draw.line(surf, WHITE, P(-w * 0.2, -h * 0.30), P(-w * 0.2, h * 0.04), 1)
        if self.rtype != "small":
            pygame.draw.circle(surf, (124, 236, 255), P(0, -h * 0.02), max(2, int(w * 0.14)))
            pygame.draw.circle(surf, OUTLINE, P(0, -h * 0.02), max(2, int(w * 0.14)), 1)
        self._bar(surf, w + 14, -h * 0.5 - 12)

        if self.state == "fuse":                             # telegrafa o raio da explosão no chão
            R = self.ground_radius
            k = 1.0 - clamp(self.fuse / self.fuse_max, 0.0, 1.0)
            pygame.draw.ellipse(surf, (255, 90, 70), (x - R, ARENA_B - R * 0.22, R * 2, R * 0.44), 1)
            rr = max(4, R * k)
            pygame.draw.ellipse(surf, (255, 214, 120), (x - rr, ARENA_B - rr * 0.22, rr * 2, rr * 0.44), 2)


# ===================================================================== BOUNCING SPHERES (e mini-esferas)
class BouncingSphere(_Ball):
    """Esfera com gravidade: quica no chão (impulso fixo por tipo → altura previsível), inverte nas paredes.
    Serve para as esferas da fase Bouncing Spheres (kind='sphere') e para as mini-esferas liberadas
    pelas cápsulas (kind='podball')."""
    mandatory = True

    def __init__(self, hz, kind, cfg, x, y, vx, vy, gravity, bounce_v, color, life=None):
        super().__init__(hz)
        self.kind = kind
        self.cfg = cfg
        self.r = float(cfg["r"])
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.gravity, self.bounce_v = gravity, bounce_v
        self.color = S.hx(color)
        self.hp = self.max_hp = float(hz.wave.scaled_hp(cfg["hp"]))
        self.points = cfg["points"]
        self.spin = random.uniform(0, math.tau)
        self.life = life                                    # None = sem validade; senão estoura sozinha (trava de segurança)
        self.hb = self._calc_hb()

    @property
    def shootable(self):
        return self.hb[3] > S.HUD_H

    def update(self, dt, mult):
        super().update(dt, mult)
        d = dt * mult
        self.vy += self.gravity * d
        self.x += self.vx * d
        self.y += self.vy * d
        self.spin += self.vx * d / max(8.0, self.r)
        if self.life is not None:
            self.life -= dt
        self.hb = self._calc_hb()

    def resolve_arena(self):
        r = self.r
        if self.x - r < ARENA_L:                            # paredes: inverte o horizontal
            self.x, self.vx = ARENA_L + r, abs(self.vx)
        elif self.x + r > ARENA_R:
            self.x, self.vx = ARENA_R - r, -abs(self.vx)
        if self.y + r >= ARENA_B:                           # chão: quica de novo (nunca "morre" no chão)
            self.y = ARENA_B - r
            self.vy = -self.bounce_v * random.uniform(0.95, 1.05)
            if r >= 20:
                self.game.fx.dust(self.x, ARENA_B, 3)
        elif self.y - r <= ARENA_T:                         # teto (abaixo do HUD)
            self.y = ARENA_T + r
            self.vy = abs(self.vy) * 0.6 + 40.0
        self.hb = self._calc_hb()

    def fx_pack(self):
        return (self.r * 2.6, "#ffffff", self.cfg.get("color", "#ff7ad9"),
                (self.cfg.get("color", "#ff7ad9"), "#ffffff", "#8d9bc2"))

    def draw(self, surf):
        x, y, r = int(self.x), int(self.y), int(self.r)
        col = self.color
        dark, light = _mix(col, (6, 10, 20), 0.62), _mix(col, WHITE, 0.62)
        draw_glow_circle(surf, x, y, r * 1.9, col, intensity=pulse(self.t, 3.2, 0.25, 0.55), layers=3)
        pygame.draw.circle(surf, OUTLINE, (x, y), r + 2)
        pygame.draw.circle(surf, dark, (x, y), r)
        pygame.draw.circle(surf, WHITE if self.flash > 0 else col, (x - r * 0.08, y - r * 0.1), max(2, r * 0.88))
        a = self.spin
        for k in (0.0, math.pi / 2):                         # costuras que giram: dão a sensação de rolagem
            ca, sa = math.cos(a + k), math.sin(a + k)
            pygame.draw.line(surf, dark, (x + ca * r * 0.92, y + sa * r * 0.92), (x - ca * r * 0.92, y - sa * r * 0.92), 2)
        pygame.draw.circle(surf, light, (x - r * 0.34, y - r * 0.38), max(2, r * 0.2))
        pygame.draw.circle(surf, OUTLINE, (x, y), r + 2, 2)
        self._bar(surf, r * 2 + 6, r + 6)


# ===================================================================== BALL POD
class BallPod(_Ball):
    kind = "pod"
    mandatory = True

    def __init__(self, hz, variant, x):
        super().__init__(hz)
        cfg = self.cfg = S.BALL_POD_TYPES[variant]
        self.variant = variant
        self.r = float(cfg["r"])
        self.hp = self.max_hp = float(hz.wave.scaled_hp(cfg["hp"]))
        self.points = cfg["points"]
        self.x = clamp(x, self.r + 20, ARENA_R - self.r - 20)
        self.spin = 0.0
        if variant == "release":
            self.y = ARENA_T - self.r
            self.target_y = random.uniform(*cfg["open_y"])
            self.vx, self.vy = 0.0, cfg["fall_speed"] * hz.diff_speed
            self.state = "descend"                          # descend -> arm -> open -> spent
            self.timer = 0.0
        else:
            self.y = ARENA_T + self.r + 6
            sp = cfg["speed"] * hz.diff_speed
            self.speed = sp
            self.vx = random.choice((-1, 1)) * sp
            self.vy = 0.0
            self.mode = "d"
            self.lane = random.uniform(*cfg["lane_y"])
            self.mode_t = random.uniform(*cfg["mode_time"])
            self.vy = random.choice((-1, 1)) * sp * cfg["diag"]
            self.state = "bounce"
            self.timer = 0.0
        self.hb = self._calc_hb()

    @property
    def shootable(self):
        return self.state in ("descend", "arm", "bounce") and self.hb[3] > S.HUD_H

    @property
    def open_k(self):
        """0 = fechada, 1 = totalmente aberta (animação mecânica)."""
        if self.state == "open":
            return clamp(self.timer / self.cfg["open_time"], 0.0, 1.0)
        return 1.0 if self.state == "spent" else 0.0

    def touches(self, hb):
        return self.state != "spent" and circle_hits_rect(self.x, self.y, self.r, hb)

    def update(self, dt, mult):
        super().update(dt, mult)
        d = dt * mult
        if self.variant == "release":
            if self.state == "descend":
                self.y += self.vy * d
                if self.y >= self.target_y:
                    self.y, self.state, self.timer = self.target_y, "arm", self.cfg["activate"]
            elif self.state == "arm":
                self.timer -= dt
                if self.timer <= 0:
                    self.state, self.timer = "open", 0.0
            elif self.state == "open":
                self.timer += dt
                if self.timer >= self.cfg["open_time"]:
                    self.hz.release_balls(self)
                    self.state, self.timer = "spent", 0.4
            elif self.state == "spent":
                self.timer -= dt
                if self.timer <= 0:
                    self.alive = False
        else:
            self.mode_t -= dt
            if self.mode_t <= 0:                            # alterna entre horizontal e diagonal
                self.mode = "h" if self.mode == "d" else "d"
                self.mode_t = random.uniform(*self.cfg["mode_time"])
                if self.mode == "h":
                    self.lane = random.uniform(*self.cfg["lane_y"])
                else:
                    self.vy = random.choice((-1, 1)) * self.speed * self.cfg["diag"]
            sx = 1 if self.vx >= 0 else -1
            if self.mode == "h":
                dy = self.lane - self.y
                self.vy = 0.0 if abs(dy) < 2 else clamp(dy * 3.0, -150.0, 150.0)
                self.vx = sx * self.speed
            else:
                self.vx = sx * self.speed * 0.85
            self.x += self.vx * d
            self.y += self.vy * d
        self.spin += (self.vx / max(8.0, self.r)) * d
        self.hb = self._calc_hb()

    def resolve_arena(self):
        if self.variant != "bounce":
            return
        r = self.r
        if self.x - r < ARENA_L:
            self.x, self.vx = ARENA_L + r, abs(self.vx)
        elif self.x + r > ARENA_R:
            self.x, self.vx = ARENA_R - r, -abs(self.vx)
        if self.y + r >= ARENA_B:
            self.y, self.vy = ARENA_B - r, -abs(self.vy)
        elif self.y - r <= ARENA_T:
            self.y, self.vy = ARENA_T + r, abs(self.vy)
        self.hb = self._calc_hb()

    def fx_pack(self):
        col = "#37c8ff" if self.variant == "release" else "#ff5c8a"
        return (self.r * 2.4, "#ffffff", col, (col, "#ffffff", "#8d9bc2"))

    # --- desenho
    def _half(self, surf, x, y, r, top, col, off):
        pts = []
        for i in range(0, 13):
            a = math.pi + math.pi * i / 12 if top else math.pi * i / 12
            pts.append((x + math.cos(a) * r, y + off + math.sin(a) * r))
        pygame.draw.polygon(surf, col, pts)
        pygame.draw.polygon(surf, OUTLINE, pts, 2)

    def draw(self, surf):
        x, y, r = self.x, self.y, self.r
        rel = self.variant == "release"
        accent = (55, 197, 220) if rel else (255, 92, 138)
        hull = WHITE if self.flash > 0 else (112, 128, 150)
        draw_glow_circle(surf, x, y, r * 1.9, accent, intensity=pulse(self.t, 3.0, 0.25, 0.6), layers=3)
        if rel and self.state == "descend":                 # propulsor no topo enquanto desce
            fl = r * (0.5 + 0.25 * math.sin(self.t * 30))
            pygame.draw.polygon(surf, (255, 214, 120), [(x - r * 0.35, y - r * 0.8), (x + r * 0.35, y - r * 0.8), (x, y - r * 0.8 - fl)])
        k = self.open_k
        if k <= 0.0:
            pygame.draw.circle(surf, OUTLINE, (int(x), int(y)), int(r) + 2)
            pygame.draw.circle(surf, hull, (int(x), int(y)), int(r))
            pygame.draw.circle(surf, _mix(hull, WHITE, 0.45), (int(x - r * 0.3), int(y - r * 0.35)), max(2, int(r * 0.22)))
            pygame.draw.line(surf, accent, (x - r, y), (x + r, y), 4)            # faixa do equador
            pygame.draw.circle(surf, OUTLINE, (int(x), int(y)), int(r), 2)
            if rel:
                lit = self.state == "arm" and int(self.t * 10) % 2 == 0
                for i in range(4):                                              # luzes de armamento
                    a = i * math.pi / 2 + math.pi / 4
                    pygame.draw.circle(surf, (255, 190, 70) if lit else (70, 56, 40),
                                       (int(x + math.cos(a) * r * 0.62), int(y + math.sin(a) * r * 0.62)), 3)
            else:
                for i in range(8):                                              # anel de bumpers girando
                    a = self.spin * 2 + i * math.tau / 8
                    pygame.draw.circle(surf, accent, (int(x + math.cos(a) * r * 0.78), int(y + math.sin(a) * r * 0.78)), 3)
                eye = pulse(self.t, 7.0, 0.5, 1.0)
                pygame.draw.circle(surf, OUTLINE, (int(x), int(y)), int(r * 0.34) + 2)
                pygame.draw.circle(surf, _mix((90, 20, 40), (255, 80, 110), eye), (int(x), int(y)), int(r * 0.34))
        else:                                                                    # abrindo: metades se afastam, núcleo brilha
            off = k * r * 0.9
            fade = 1.0 if self.state == "open" else clamp(self.timer / 0.4, 0.0, 1.0)
            core = (255, 236, 150)
            pygame.draw.circle(surf, core, (int(x), int(y)), int(r * (0.35 + 0.35 * k * fade)))
            draw_glow_circle(surf, x, y, r * 1.5 * (0.6 + 0.6 * k), (255, 214, 120), intensity=0.9 * fade, layers=3)
            self._half(surf, x, y, r, True, _mix(hull, OUTLINE, 1 - fade * 0.6 if self.state == "spent" else 0.0), -off)
            self._half(surf, x, y, r, False, _mix(hull, OUTLINE, 1 - fade * 0.6 if self.state == "spent" else 0.0), off)
        self._bar(surf, r * 2 + 6, r + 7)


# ===================================================================== BLACK SAW
class _RailPath:
    """Trilho retangular de cantos arredondados (centro das serras): top → direita → base → esquerda,
    em sentido horário. point(s) devolve (x, y) para uma distância s ao longo do perímetro."""

    def __init__(self):
        cfg = S.BLACK_SAW
        r, m = cfg["radius"], cfg["margin"]
        self.l = r + m
        self.rr = S.WIDTH - self.l
        self.t = S.HUD_H + r + m
        self.b = S.GROUND_Y - r + 2
        self.cr = min(cfg["corner_radius"], (self.rr - self.l) / 2 - 1, (self.b - self.t) / 2 - 1)
        self.A = (self.rr - self.l) - 2 * self.cr
        self.B = (self.b - self.t) - 2 * self.cr
        self.arc = math.pi * self.cr / 2
        self.length = 2 * self.A + 2 * self.B + 4 * self.arc

    def point(self, s):
        s %= self.length
        l, rr, t, b, cr, A, B, arc = self.l, self.rr, self.t, self.b, self.cr, self.A, self.B, self.arc
        if s < A:
            return (l + cr + s, t)
        s -= A
        if s < arc:
            a = -math.pi / 2 + s / cr
            return (rr - cr + math.cos(a) * cr, t + cr + math.sin(a) * cr)
        s -= arc
        if s < B:
            return (rr, t + cr + s)
        s -= B
        if s < arc:
            a = s / cr
            return (rr - cr + math.cos(a) * cr, b - cr + math.sin(a) * cr)
        s -= arc
        if s < A:
            return (rr - cr - s, b)
        s -= A
        if s < arc:
            a = math.pi / 2 + s / cr
            return (l + cr + math.cos(a) * cr, b - cr + math.sin(a) * cr)
        s -= arc
        if s < B:
            return (l, b - cr - s)
        s -= B
        a = math.pi + s / cr
        return (l + cr + math.cos(a) * cr, t + cr + math.sin(a) * cr)

    def draw(self, surf):
        pygame.draw.rect(surf, (40, 66, 82), (self.l, self.t, self.rr - self.l, self.b - self.t), 2,
                         border_radius=int(self.cr))


class BlackSaw(_Ball):
    kind = "blacksaw"

    def __init__(self, hz, s0, direction):
        super().__init__(hz)
        cfg = self.cfg = S.BLACK_SAW
        self.r = float(cfg["radius"])
        self.s, self.dir = s0, direction
        self.warn = cfg["spawn_warn"]                       # telegrafa: parada e inofensiva antes de armar
        self.armed = False
        self.angle = random.uniform(0, math.tau)
        self.spark_t = random.uniform(*cfg["spark_interval"])
        if cfg["destructible"]:
            self.hp = self.max_hp = float(hz.wave.scaled_hp(cfg["hp"]))
        self.x, self.y = hz.path.point(s0)
        self.hb = self._calc_hb()

    @property
    def shootable(self):
        return bool(self.cfg["destructible"]) and self.armed and self.hb[3] > S.HUD_H

    def touches(self, hb):
        return self.armed and circle_hits_rect(self.x, self.y, self.r * self.cfg["hit_scale"], hb)

    def on_player_contact(self, g, p):
        if p.take_hit():
            g.fx.sparks(self.x, self.y, "#ffb04a", 6, up=False)

    def update(self, dt, mult):
        super().update(dt, mult)
        if not self.armed:
            self.warn -= dt
            self.angle += dt * 5.0
            if self.warn <= 0:
                self.armed = True
        else:
            v = self.cfg["speed"] * self.hz.diff_speed * mult
            self.s += self.dir * v * dt
            self.angle += self.dir * v * dt / self.r * 1.4
            self.spark_t -= dt
            if self.spark_t <= 0:
                self.spark_t = random.uniform(*self.cfg["spark_interval"])
                if self.game.fx.level < 2:
                    self.game.fx.sparks(self.x, self.y, "#ffb04a", 1, up=(self.y > S.GROUND_Y - self.r * 2.5))
        self.x, self.y = self.hz.path.point(self.s)
        self.hb = self._calc_hb()

    def fx_pack(self):
        return (self.r * 2.2, "#ffffff", "#ffb04a", ("#ffb04a", "#8d9bc2", "#ffffff"))

    def draw(self, surf):
        x, y, r = self.x, self.y, self.r
        armed = self.armed
        n = self.cfg["teeth"]
        step = math.tau / n
        blink = (not armed) and int(self.t * 8) % 2 == 0
        draw_glow_circle(surf, x, y, r * 1.8, (255, 112, 50), intensity=pulse(self.t, 5.0, 0.28, 0.6) if armed else 0.25, layers=3)
        pts = []
        ri = r * 0.80
        for i in range(n):                                  # dentes em "rampa": subida suave, queda abrupta
            a0 = self.angle + i * step
            pts.append((x + math.cos(a0) * ri, y + math.sin(a0) * ri))
            a1 = a0 + step * 0.86
            pts.append((x + math.cos(a1) * r, y + math.sin(a1) * r))
        body = (58, 68, 88) if armed else (48, 54, 68)
        pygame.draw.polygon(surf, WHITE if self.flash > 0 else body, pts)
        pygame.draw.polygon(surf, (196, 214, 232) if armed else (120, 130, 148), pts, 2)
        pygame.draw.circle(surf, (24, 30, 44), (int(x), int(y)), int(r * 0.52))
        pygame.draw.circle(surf, (255, 150, 60) if (armed or blink) else (110, 90, 70), (int(x), int(y)), int(r * 0.52), 3)
        for i in range(4):                                  # raios do hub
            a = self.angle * 1.0 + i * math.pi / 2
            pygame.draw.line(surf, (120, 140, 160), (x + math.cos(a) * r * 0.2, y + math.sin(a) * r * 0.2),
                             (x + math.cos(a) * r * 0.48, y + math.sin(a) * r * 0.48), 2)
        core = pulse(self.t, 7.0, 0.6, 1.0)
        pygame.draw.circle(surf, _mix((140, 60, 30), (255, 190, 90), core), (int(x), int(y)), max(3, int(r * 0.2)))
        pygame.draw.circle(surf, WHITE, (int(x), int(y)), max(1, int(r * 0.08)))
        if not armed:                                       # anel de aviso enquanto ainda não está armada
            rr = int(r * (1.1 + 0.5 * (1.0 - clamp(self.warn / self.cfg["spawn_warn"], 0.0, 1.0))))
            pygame.draw.circle(surf, (255, 190, 90) if blink else (255, 90, 60), (int(x), int(y)), rr, 2)
        self._bar(surf, r * 2, r + 6)


# ===================================================================== gerenciador de fases
def plan_for(n):
    """Plano de hazards do round n: dict(saws, order, scale, cfg). Rounds > 10 (modo infinito) reciclam
    S.HAZARD_ENDLESS_CYCLE com intensidade crescente."""
    scale = 1.0
    if n in S.HAZARD_ROUNDS:
        base = S.HAZARD_ROUNDS[n]
    elif n > 10:
        cyc = S.HAZARD_ENDLESS_CYCLE
        base = S.HAZARD_ROUNDS[cyc[(n - 11) % len(cyc)]]
        scale = min(S.HAZARD_ENDLESS_MAX_SCALE, 1.0 + S.HAZARD_ENDLESS_GROWTH * (n - 10))
    else:
        base = {}
    saws = int(base.get("saws", 0))
    if saws > 0 and scale >= 1.5:
        saws += 1
    order = tuple(ph for ph in base.get("order", ()) if ph in base and ph in S.HAZARD_PHASES)
    return dict(saws=min(4, saws), order=order, scale=scale, cfg=base)


class HazardManager:
    def __init__(self, wave):
        self.wave, self.game = wave, wave.game
        self.path = _RailPath()
        self.reset()

    # ------------------------------------------------------------ estado
    def reset(self):
        self.saws, self.rockets, self.pods, self.balls, self.spheres = [], [], [], [], []
        self.plan = None
        self.order = []
        self.sequence_active = False
        self.sequence_done = False
        self.stage = "idle"          # idle | warn | run | resolve | cleared
        self.phase = None
        self.phase_cfg = {}
        self.stage_t = 0.0
        self.phase_t = 0.0
        self.run_t = 0.0
        self.spawn_t = 0.0
        self.resolve_pause = 0.0
        self.queue = []
        self.last_rocket_x = None

    @property
    def diff_speed(self):
        return self.game.diff["enemy_speed"]

    def player_scale(self):
        return 1.0 + S.HAZARD_PLAYER_SCALE * max(0, len(self.game.players) - 1)

    def total_scale(self):
        return (self.plan["scale"] if self.plan else 1.0) * self.player_scale()

    def all_alive(self):
        for lst in (self.saws, self.pods, self.balls, self.spheres, self.rockets):
            for h in lst:
                if h.alive:
                    yield h

    def any_active(self):
        return bool(self.saws or self.pods or self.balls or self.spheres or self.rockets)

    def shootables(self):
        return [h for h in self.all_alive() if h.shootable]

    def threat_points(self):
        """(x, y, raio) de cada hazard vivo: usado para escolher um ponto de renascimento seguro."""
        return [(h.x, h.y, h.r + (h.ground_radius * 0.6 if isinstance(h, Rocket) else 0.0)) for h in self.all_alive()]

    def pending_mandatory(self):
        """Quantos hazards obrigatórios (ainda não resolvidos) existem — inclui os que ainda vão nascer."""
        n = sum(1 for p in self.pods if p.alive) + sum(1 for b in self.balls if b.alive) \
            + sum(1 for s in self.spheres if s.alive)
        return n + len(self.queue)

    # ------------------------------------------------------------ início do combate: serras
    def on_combat_start(self, round_no):
        """Chamado quando os inimigos do round nascem. As Black Saws entram AGORA (junto do combate)."""
        self.reset()
        self.plan = plan_for(round_no)
        n = self.plan["saws"]
        if n <= 0:
            return
        cfg = S.BLACK_SAW
        base = random.uniform(0, self.path.length)
        for i in range(n):
            d = -1 if (cfg["alternate_direction"] and i % 2 == 1) else 1
            saw = BlackSaw(self, base + i * self.path.length / n, d)
            self.saws.append(saw)
            self.game.fx.ring(saw.x, saw.y, 8, 54, "#ffb04a", 0.6, 3)

    # ------------------------------------------------------------ fim do combate: fases
    def begin_sequence(self):
        """O combate acabou. True se há fases de hazard a rodar neste round; False = round termina direto."""
        if self.plan is None or not self.plan["order"]:
            self.sequence_done = True
            return False
        self.order = list(self.plan["order"])
        self.sequence_active, self.sequence_done = True, False
        self._start_warn(self.order.pop(0))
        return True

    def _start_warn(self, phase):
        g = self.game
        info = S.HAZARD_PHASES[phase]
        self.phase = phase
        self.phase_cfg = self.plan["cfg"][phase]
        self.stage, self.stage_t, self.phase_t = "warn", info["warn"], 0.0
        g.show_banner(info["banner"], info["sub"], info["color"], info["warn"] + 0.2, alert=True, compact=True)
        g.audio.on_boss_warning()

    def _start_phase(self):
        c, sc = self.phase_cfg, self.total_scale()
        self.stage, self.phase_t, self.run_t = "run", 0.0, 0.0
        self.last_rocket_x = None
        if self.phase == "rockets":
            self.spawn_t = 0.5
        elif self.phase == "ball_pod":
            pods = list(c["pods"])
            want = max(len(pods), int(round(len(pods) * sc)))
            self.queue = [pods[i % len(pods)] for i in range(want)]
            self.spawn_t = 0.3
        elif self.phase == "spheres":
            lst = []
            for stype, cnt in c["mix"]:
                lst += [stype] * max(1, int(round(cnt * sc)))
            random.shuffle(lst)
            self.queue = lst
            self.spawn_t = 0.3

    def _finish_phase(self):
        g, c = self.game, S.HAZARD_CLEARED
        self.stage, self.stage_t = "cleared", c["time"]
        self.queue = []
        g.show_banner(c["title"], c["sub"], c["color"], c["time"], compact=True)
        g.flash(c["color"], 0.15)
        if self.order:
            g.audio.on_round_clear()

    def _next_after_clear(self):
        if self.order:
            self._start_warn(self.order.pop(0))
        else:
            self.stage, self.phase = "idle", None
            self.sequence_active, self.sequence_done = False, True

    def clear_round(self):
        """Round concluído: as serras (e qualquer resto) saem de cena."""
        g = self.game
        for h in list(self.all_alive()):
            if isinstance(h, BlackSaw):
                g.fx.explosion(h.x, h.y, h.r * 1.6, "#ffffff", "#ffb04a", ("#ffb04a", "#8d9bc2", "#ffffff"))
                h.alive = False
            else:
                h.force_clear(g)
        self.reset()

    def _force_clear_phase(self):
        for lst in (self.pods, self.balls, self.spheres, self.rockets):
            for h in lst:
                if h.alive:
                    h.force_clear(self.game)
        self.queue = []

    # ------------------------------------------------------------ spawn
    def _pick_rocket_x(self):
        c = S.ROCKET_RAIN
        m = c["margin"]
        for _ in range(6):
            al = self.game.alive_players()
            if al and random.random() < c["aim_chance"]:
                x = random.choice(al).x + random.uniform(-c["aim_spread"], c["aim_spread"])
            else:
                x = random.uniform(m, S.WIDTH - m)
            x = clamp(x, m, S.WIDTH - m)
            if self.last_rocket_x is None or abs(x - self.last_rocket_x) >= c["min_gap"]:
                break
        self.last_rocket_x = x
        return x

    def _spawn_rocket(self):
        c = self.phase_cfg
        types, weights = zip(*c["mix"])
        rtype = random.choices(types, weights=weights)[0]
        lo, hi = S.ROCKET_TYPES[rtype]["speed"]
        speed = random.uniform(lo, hi) * self.game.diff["proj_speed"] * c.get("speed_mult", 1.0)
        vx = random.uniform(-S.ROCKET_RAIN["drift"], S.ROCKET_RAIN["drift"])
        self.rockets.append(Rocket(self, rtype, self._pick_rocket_x(), vx, speed))

    def _spawn_pod(self, variant):
        pod = BallPod(self, variant, random.uniform(120, S.WIDTH - 120))
        self.pods.append(pod)
        self.game.fx.ring(pod.x, max(pod.y, S.HUD_H + 20), 6, 46, "#37c8ff", 0.5, 3)

    def release_balls(self, pod):
        """Abertura da cápsula: libera as mini-esferas (entram na própria fase Ball Pod, são obrigatórias)."""
        g, pc = self.game, S.POD_BALL
        lo, hi = self.phase_cfg.get("balls", pod.cfg["balls"])
        n = random.randint(lo, hi)
        dirs = [-1, 1] * n
        random.shuffle(dirs)
        for i in range(n):
            vx = dirs[i] * random.uniform(*pc["speed_x"]) * self.diff_speed * (0.6 + 0.4 * (i + 1) / n)
            vy = -random.uniform(*pc["burst_v"])
            self.balls.append(BouncingSphere(self, "podball", pc, pod.x, pod.y, vx, vy, pc["gravity"],
                                              pc["bounce_v"], "#ff7ad9", life=pc["life"]))
        g.fx.ring(pod.x, pod.y, 8, 90, "#ffe9a0", 0.5, 4)
        g.fx.sparks(pod.x, pod.y, "#ffe9a0", 8, up=False)
        g.audio.on_explosion(big=False)

    def _spawn_sphere(self, stype):
        cfg = S.SPHERE_TYPES[stype]
        m = S.SPHERE_SPAWN["margin"]
        x = random.uniform(m, S.WIDTH - m)
        y = random.uniform(*S.SPHERE_SPAWN["y"])
        vx = random.choice((-1, 1)) * random.uniform(*cfg["speed_x"]) * self.diff_speed
        self.spheres.append(BouncingSphere(self, "sphere", cfg, x, y, vx, 0.0, S.SPHERE_GRAVITY,
                                            cfg["bounce_v"], cfg["color"]))
        self.game.fx.ring(x, y, 6, cfg["r"] * 2.6, cfg["color"], 0.45, 3)

    # ------------------------------------------------------------ atualização
    def update(self, dt):
        self._update_entities(dt)
        if not self.sequence_active:
            return
        if self.stage == "warn":
            self.stage_t -= dt
            if self.stage_t <= 0:
                self._start_phase()
        elif self.stage == "run":
            self.phase_t += dt
            getattr(self, "_run_" + self.phase)(dt)
            if self.stage == "run" and self.phase_t > S.HAZARD_PHASE_TIMEOUT:      # trava anti-impasse
                self._force_clear_phase()
                self._finish_phase()
        elif self.stage == "resolve":                       # foguetes: espera os últimos se resolverem
            self.stage_t += dt
            if not any(r.alive for r in self.rockets):
                self.resolve_pause -= dt
                if self.resolve_pause <= 0:
                    self._finish_phase()
            elif self.stage_t > S.HAZARD_RESOLVE_TIMEOUT:
                self._force_clear_phase()
        elif self.stage == "cleared":
            self.stage_t -= dt
            if self.stage_t <= 0:
                self._next_after_clear()

    def _update_entities(self, dt):
        g = self.game
        mv, mp = g.enemy_move_mult, g.enemy_proj_mult
        for h in self.saws:
            h.update(dt, mv)
        for h in self.pods:
            h.update(dt, mv)
        for h in self.spheres:
            h.update(dt, mv)
        for h in self.balls:
            h.update(dt, mv)
            if h.alive and h.life is not None and h.life <= 0:       # mini-esfera que ninguém acertou: estoura
                h.force_clear(g)
        for h in self.rockets:
            h.update(dt, mp)
            if h.alive and h.state == "fuse" and h.fuse <= 0:      # pavio acabou: detona no chão
                g.hazard_blast(h, "ground")
        for lst in ("saws", "pods", "balls", "spheres", "rockets"):
            cur = getattr(self, lst)
            if cur:
                keep = [h for h in cur if h.alive and self._sane(h)]
                if len(keep) != len(cur):
                    setattr(self, lst, keep)

    @staticmethod
    def _sane(h):
        """Descarta objetos corrompidos/fora do mundo (NaN, escaparam da arena) para nunca prender a fase."""
        x, y = h.x, h.y
        if x != x or y != y or abs(x) > S.WIDTH * 2 or y > S.HEIGHT * 2 or y < -S.HEIGHT:
            h.alive = False
            print("[hazards] objeto fora do mundo descartado:", h.kind)
            return False
        return True

    # ------------------------------------------------------------ fases em execução
    def _run_rockets(self, dt):
        c, sc = self.phase_cfg, self.total_scale()
        self.run_t += dt
        if self.run_t >= c["duration"]:
            self.stage, self.stage_t = "resolve", 0.0              # acabou o tempo: para de gerar e resolve o resto
            self.resolve_pause = S.HAZARD_RESOLVE_PAUSE
            return
        self.spawn_t -= dt
        alive = sum(1 for r in self.rockets if r.alive)
        if self.spawn_t <= 0 and alive < max(1, int(round(c["max_alive"] * sc))):
            self._spawn_rocket()
            self.spawn_t = random.uniform(*c["interval"]) / sc

    def _run_ball_pod(self, dt):
        self.spawn_t -= dt
        if self.queue and self.spawn_t <= 0:
            self._spawn_pod(self.queue.pop(0))
            self.spawn_t = self.phase_cfg.get("stagger", 1.5)
        if self.pending_mandatory() == 0:
            self._finish_phase()

    def _run_spheres(self, dt):
        self.spawn_t -= dt
        if self.queue and self.spawn_t <= 0:
            self._spawn_sphere(self.queue.pop(0))
            self.spawn_t = self.phase_cfg.get("stagger", 0.5)
        if self.pending_mandatory() == 0:
            self._finish_phase()

    # ------------------------------------------------------------ HUD / desenho
    def hud_lines(self):
        """[(texto, cor)] curtos para o HUD (centro, abaixo do indicador de round)."""
        if not self.sequence_active or self.phase is None:
            return []
        info = S.HAZARD_PHASES[self.phase]
        col = S.hx(info["color"])
        if self.stage == "run" and self.phase == "rockets":
            left = max(0.0, self.phase_cfg["duration"] - self.run_t)
            return [(f"{info['hud']}  {left:0.0f}s", col)]
        if self.stage == "resolve":
            return [(f"{info['hud']}  ...", col)]
        if self.stage == "run":
            return [(f"{info['hud']}  RESTAM {self.pending_mandatory()}", col)]
        return []

    def draw(self, surf):
        if self.saws:
            self.path.draw(surf)
        for lst in (self.saws, self.pods, self.spheres, self.balls, self.rockets):
            for h in lst:
                if h.alive:
                    h.draw(surf)
