"""
projectile.py — projétil genérico, parametrizado (porte de Projectile em
main.py). owner=Player é tiro do jogador; owner=None é projétil inimigo,
onde 'kind' define o comportamento (bomb, bullet, rocket, orb, jetbomb).
"""
import math

import pygame

import settings as S

PROJ_SIZES = {"shot": (6, 24), "bomb": (14, 20), "bullet": (12, 12), "rocket": (14, 28),
              "jetbomb": (20, 28), "orb": (28, 28)}


class Projectile:
    def __init__(self, owner, x, y, vy, vx=0.0, damage=S.SHOT_DAMAGE, kind=None, style=None,
                 w=None, h=None, color=None, hp=None, blast=0.0, air_blast=0.0, fuse=None,
                 spiral=None, max_range=None):
        self.owner = owner
        self.kind = kind or ("shot" if owner is not None else "bomb")
        self.style = style or ("bullet" if self.kind == "shot" else self.kind)
        dw, dh = PROJ_SIZES.get(self.kind, (14, 20))
        self.w, self.h = w or dw, h or dh
        self.x, self.y = x, y
        self.prev_x, self.prev_y = x, y
        self.vx, self.vy = vx, vy
        self.damage = damage
        self.color = S.hx(color) if color else None
        self.hp = self.max_hp = hp
        self.blast, self.air_blast = blast, air_blast
        self.fuse = fuse
        self.spiral = spiral
        self.range = max_range
        self.travel = 0.0
        self.t = 0.0
        self.alive = True
        self.exploded = False
        self.flash = 0.0
        self.hb = self._calc_hb()

    def _calc_hb(self):
        hw, hh = self.w / 2, self.h / 2
        return (min(self.x, self.prev_x) - hw, min(self.y, self.prev_y) - hh,
                max(self.x, self.prev_x) + hw, max(self.y, self.prev_y) + hh)

    def hitbox(self):
        return self.hb

    def update(self, dt, mult=1.0):
        """mult = multiplicador dinâmico de velocidade dos ataques inimigos (boosts); 1.0 para tiros dos jogadores."""
        self.prev_x, self.prev_y = self.x, self.y
        self.t += dt
        if self.flash > 0:
            self.flash -= dt
        sp = self.spiral
        if sp is not None:
            sp["gx"] += sp["gvx"] * dt * mult
            sp["gy"] += sp["gvy"] * dt * mult
            r = sp["r0"] + (sp["r1"] - sp["r0"]) * min(1.0, self.t / sp["grow"])
            th = sp["phase"] + sp["omega"] * self.t
            self.x = sp["gx"] + r * math.cos(th)
            self.y = sp["gy"] + r * 0.6 * math.sin(th)
        else:
            self.x += self.vx * dt * mult
            self.y += self.vy * dt * mult
        if self.fuse is not None:
            self.fuse -= dt
        if self.range is not None:
            self.travel += math.hypot(self.x - self.prev_x, self.y - self.prev_y)
            if self.travel >= self.range:
                self.alive = False
        self.hb = self._calc_hb()

    def hit(self, dmg):
        """Dano em projétil destrutível. Retorna True quando a vida chega a zero."""
        if self.hp is None or not self.alive or self.exploded:
            return False
        self.hp -= dmg
        self.flash = 0.08
        return self.hp <= 1e-9

    # ------------------------------------------------------------ desenho
    @staticmethod
    def _tint(color, target, amount):
        """Mistura duas cores RGB sem depender de assets externos."""
        amount = max(0.0, min(1.0, amount))
        return tuple(
            max(0, min(255, int(color[i] * (1 - amount) + target[i] * amount)))
            for i in range(3)
        )

    def draw(self, surf):
        k = self.kind
        x, y = int(self.x), int(self.y)
        white = (248, 252, 255)
        pale = (218, 242, 255)

        # Prioriza a cor configurada para a arma; cada tipo recebe um desenho
        # próprio, mas mantém a mesma família cromática.
        if k == "shot":
            col = self.color or (self.owner.color if self.owner else (120, 220, 255))
            col = tuple(col[:3])
            core = self.owner.cfg.get("bullet_core", white) if (self.owner and self.color is None) else white
            core = S.hx(core) if isinstance(core, str) else core
            w, h = int(self.w), int(self.h)
            if self.style == "pellet":
                pygame.draw.circle(surf, self._tint(col, white, 0.18), (x, y), max(3, int(w / 2) + 2))
                pygame.draw.circle(surf, col, (x, y), max(2, int(w / 2)))
                pygame.draw.circle(surf, white, (x - 1, y - 1), max(1, min(3, int(w / 4))))
            elif self.style == "beam":
                beam = pygame.Rect(x - w // 2 - 3, y - h // 2, w + 6, h)
                pygame.draw.rect(surf, self._tint(col, white, 0.22), beam, border_radius=5)
                pygame.draw.rect(surf, col, beam.inflate(-3, -2), border_radius=4)
                pygame.draw.rect(surf, white, (x - max(1, w // 5), y - h // 2 + 4, max(2, w * 2 // 5), max(2, h - 8)), border_radius=3)
            else:
                body = pygame.Rect(x - w // 2, y - h // 2, max(4, w), max(8, h))
                pygame.draw.rect(surf, self._tint(col, white, 0.35), body.inflate(4, 2), border_radius=max(3, w // 2))
                pygame.draw.rect(surf, col, body, border_radius=max(2, w // 2))
                pygame.draw.rect(surf, core, body.inflate(-max(2, w // 2), -5), border_radius=3)
                pygame.draw.circle(surf, white, (x, y - h // 2 + 3), 2)

        elif k == "bomb":
            col = self.color or (255, 170, 92)
            col = tuple(col[:3])
            light = self._tint(col, white, 0.48)
            # Cauda curta e arredondada, com núcleo luminoso.
            pygame.draw.polygon(surf, self._tint(col, white, 0.18),
                                [(x - 5, y - 7), (x - 2, y - 18), (x + 2, y - 18), (x + 5, y - 7)])
            pygame.draw.ellipse(surf, self._tint(col, (255, 255, 255), 0.25),
                                (x - 10, y - 11, 20, 22))
            pygame.draw.ellipse(surf, col, (x - 8, y - 9, 16, 18))
            pygame.draw.ellipse(surf, light, (x - 5, y - 6, 6, 7))
            pygame.draw.circle(surf, white, (x + 3, y + 4), 2)

        elif k == "bullet":
            col = self.color or (255, 135, 220)
            col = tuple(col[:3])
            pygame.draw.circle(surf, self._tint(col, white, 0.45), (x, y), 10)
            pygame.draw.circle(surf, col, (x, y), 8)
            pygame.draw.circle(surf, self._tint(col, white, 0.65), (x - 2, y - 2), 4)
            pygame.draw.circle(surf, white, (x - 2, y - 2), 2)

        elif k == "rocket":
            col = self.color or (255, 174, 105)
            col = tuple(col[:3])
            light = self._tint(col, white, 0.62)
            fin = self._tint(col, (255, 255, 255), 0.25)
            # Silhueta compacta de foguete: ponta, corpo colorido e aletas.
            pygame.draw.polygon(surf, fin, [(x, y - 17), (x + 8, y - 7), (x + 7, y + 9),
                                           (x, y + 14), (x - 7, y + 9), (x - 8, y - 7)])
            body = white if self.flash > 0 else col
            pygame.draw.polygon(surf, body, [(x, y - 14), (x + 5, y - 6), (x + 5, y + 8),
                                              (x, y + 11), (x - 5, y + 8), (x - 5, y - 6)])
            pygame.draw.polygon(surf, light, [(x, y - 12), (x + 2, y - 5), (x + 1, y + 5),
                                               (x - 1, y + 5), (x - 2, y - 5)])
            pygame.draw.polygon(surf, fin, [(x - 5, y + 4), (x - 11, y + 12), (x - 5, y + 10)])
            pygame.draw.polygon(surf, fin, [(x + 5, y + 4), (x + 11, y + 12), (x + 5, y + 10)])
            flame_len = 7 + int(3 * (0.5 + 0.5 * math.sin(self.t * 22)))
            pygame.draw.polygon(surf, (255, 210, 125), [(x - 3, y + 10), (x, y + 10 + flame_len), (x + 3, y + 10)])
            pygame.draw.polygon(surf, white, [(x - 1, y + 10), (x, y + 10 + max(3, flame_len - 3)), (x + 1, y + 10)])

        elif k == "jetbomb":
            col = self.color or (133, 190, 255)
            col = tuple(col[:3])
            light = self._tint(col, white, 0.52)
            body = white if self.flash > 0 else col
            # Bomba de maior porte com faixa de identificação e detalhes claros.
            pygame.draw.polygon(surf, self._tint(col, white, 0.25),
                                [(x - 6, y - 9), (x - 10, y + 2), (x - 7, y + 11),
                                 (x, y + 15), (x + 7, y + 11), (x + 10, y + 2), (x + 6, y - 9)])
            pygame.draw.ellipse(surf, body, (x - 11, y - 12, 22, 25))
            pygame.draw.ellipse(surf, light, (x - 7, y - 9, 7, 9))
            pygame.draw.rect(surf, self._tint(col, white, 0.18), (x - 10, y - 2, 20, 6), border_radius=3)
            pygame.draw.line(surf, white, (x - 5, y + 1), (x + 5, y + 1), 2)
            if self.hp is not None and self.hp < self.max_hp:
                ratio = max(0.0, self.hp / self.max_hp)
                x0, y0 = x - 12, y + 16
                pygame.draw.rect(surf, (25, 35, 52), (x0, y0, 24, 5), border_radius=2)
                hp_col = (113, 235, 160) if ratio > 0.5 else (255, 213, 115) if ratio > 0.25 else (255, 125, 135)
                pygame.draw.rect(surf, hp_col, (x0 + 1, y0 + 1, int(22 * ratio), 3), border_radius=2)

        elif k == "orb":
            col = self.color or (255, 130, 170)
            col = tuple(col[:3])
            light = self._tint(col, white, 0.60)
            r = max(16, int(self.blast))
            warn = self.fuse is not None and self.fuse <= S.FINALBOSS["orb_warn"]
            if warn and int(self.t * 10) % 2 == 0:
                pygame.draw.circle(surf, self._tint(col, white, 0.35), (x, y), r, width=3)
            pygame.draw.circle(surf, self._tint(col, white, 0.22), (x, y), 18)
            pygame.draw.circle(surf, col, (x, y), 14)
            pygame.draw.circle(surf, light, (x - 3, y - 3), 8)
            core_col = (255, 246, 190) if int(self.t * 6) % 2 == 0 else white
            pygame.draw.circle(surf, core_col, (x, y), 5)
