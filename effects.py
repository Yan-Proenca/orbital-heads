"""
effects.py — sistema de partículas otimizado e estilizado (explosões, estilhaços,
textos flutuantes, anéis, rastro de dash de alta energia cibernética).
"""
import math
import random

import pygame

import settings as S
from utils import clamp

LOD_START = 24   # "carga" (inimigos + 0.5*projéteis) a partir da qual o teto de partículas começa a cair
LOD_FULL = 70     # carga em que o teto chega ao mínimo


# ----------------------------------------------------------------- partículas individuais
class _Particle:
    def update(self, dt):
        """Retorna True se ainda viva."""
        raise NotImplementedError

    def draw(self, surf):
        raise NotImplementedError


class Debris(_Particle):
    """Estilhaço: ponto/retângulo energizado com gravidade e atrito leve."""

    def __init__(self, x, y, vx, vy, size, color, life, gravity=600.0):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.size = size
        self.color = S.hx(color)
        self.life = self.max_life = life
        self.gravity = gravity

    def update(self, dt):
        self.life -= dt
        if self.life <= 0:
            return False
        self.vy += self.gravity * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        return True

    def draw(self, surf):
        a = clamp(self.life / self.max_life, 0.0, 1.0)
        r = max(1, int(self.size * a))
        # Desenha com efeito de brilho suave nas partículas maiores
        surf_part = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
        pygame.draw.rect(surf_part, (*self.color, int(255 * a)), (1, 1, r, r))
        surf.blit(surf_part, (int(self.x - r / 2), int(self.y - r / 2)))


class Ring(_Particle):
    """Anel (ou disco preenchido) que se expande com efeito de onda de choque sci-fi."""

    def __init__(self, x, y, r0, r1, color, life, width=3, filled=False):
        self.x, self.y = x, y
        self.r0, self.r1 = r0, r1
        self.color = S.hx(color)
        self.life = self.max_life = life
        self.width = width
        self.filled = filled

    def update(self, dt):
        self.life -= dt
        return self.life > 0

    def draw(self, surf):
        t = 1.0 - clamp(self.life / self.max_life, 0.0, 1.0)
        r = int(self.r0 + (self.r1 - self.r0) * t)
        if r <= 0:
            return
        alpha = int(255 * clamp(self.life / self.max_life, 0.0, 1.0))
        ring_surf = pygame.Surface((r * 2 + 6, r * 2 + 6), pygame.SRCALPHA)
        color = (*self.color, alpha)
        if self.filled:
            pygame.draw.circle(ring_surf, color, (r + 3, r + 3), r)
        else:
            pygame.draw.circle(ring_surf, color, (r + 3, r + 3), r, width=max(1, self.width))
        surf.blit(ring_surf, (int(self.x - r - 3), int(self.y - r - 3)))


class Ghost(_Particle):
    """Silhueta holográfica detalhada do jogador durante o dash."""

    def __init__(self, x, y, color, life):
        self.x, self.y = x, y
        self.color = S.hx(color)
        self.life = self.max_life = life

    def update(self, dt):
        self.life -= dt
        return self.life > 0

    def draw(self, surf):
        alpha = int(160 * clamp(self.life / self.max_life, 0.0, 1.0))
        w, h = 30, 60
        ghost_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        # Desenha uma silhueta com contorno futurista translúcido
        pygame.draw.rect(ghost_surf, (*self.color, alpha), (4, 4, w - 8, h - 8), border_radius=4)
        pygame.draw.rect(ghost_surf, (255, 255, 255, alpha), (8, 12, w - 16, 12), border_radius=3)
        surf.blit(ghost_surf, (int(self.x - w / 2), int(self.y - h)))


class Streak(_Particle):
    """Risco de velocidade energizado (rastro estilo neon para o dash)."""

    def __init__(self, x, y, vx, color, life):
        self.x, self.y = x, y
        self.vx = vx
        self.color = S.hx(color)
        self.life = self.max_life = life

    def update(self, dt):
        self.life -= dt
        self.x += self.vx * dt
        return self.life > 0

    def draw(self, surf):
        alpha = int(220 * clamp(self.life / self.max_life, 0.0, 1.0))
        length = 24
        streak_surf = pygame.Surface((length, 4), pygame.SRCALPHA)
        pygame.draw.rect(streak_surf, (*self.color, alpha), (0, 0, length, 4), border_radius=2)
        pygame.draw.rect(streak_surf, (255, 255, 255, int(alpha * 0.8)), (2, 1, length - 4, 2), border_radius=1)
        surf.blit(streak_surf, (int(self.x - length / 2), int(self.y)))


class FloatText(_Particle):
    """Texto flutuante estilizado (pontos, avisos e bônus)."""
    _font_cache = {}

    def __init__(self, x, y, text, color, size=22, life=0.9):
        self.x, self.y = x, y
        self.text = text
        self.color = S.hx(color)
        self.size = size
        self.life = self.max_life = life
        self.vy = -50.0

    def _font(self):
        f = self._font_cache.get(self.size)
        if f is None:
            f = pygame.font.SysFont(S.FONT_UI_NAME, self.size, bold=True)
            self._font_cache[self.size] = f
        return f

    def update(self, dt):
        self.life -= dt
        self.y += self.vy * dt
        self.vy *= 0.97
        return self.life > 0

    def draw(self, surf):
        alpha = int(255 * clamp(self.life / self.max_life, 0.0, 1.0))
        font = self._font()
        # Sombra preta para destacar o texto sobre o cenário
        shadow = font.render(self.text, True, (0, 0, 0))
        shadow.set_alpha(alpha)
        surf.blit(shadow, shadow.get_rect(center=(int(self.x) + 1, int(self.y) + 1)))

        img = font.render(self.text, True, self.color)
        img.set_alpha(alpha)
        surf.blit(img, img.get_rect(center=(int(self.x), int(self.y))))


# ----------------------------------------------------------------- gerenciador
class Effects:
    """Gerencia partículas com suporte adaptativo de desempenho e estilo visual coeso."""

    def __init__(self):
        self.items = []
        self.limit = S.MAX_PARTICLES
        self.level = 0
        self._load = 0.0

    def set_load(self, load, level=0):
        self._load, self.level = load, level
        if load <= LOD_START:
            lim = S.MAX_PARTICLES
        elif load >= LOD_FULL:
            lim = S.MIN_PARTICLES
        else:
            lim = S.MAX_PARTICLES + (S.MIN_PARTICLES - S.MAX_PARTICLES) * (load - LOD_START) / (LOD_FULL - LOD_START)
        self.limit = max(S.MIN_PARTICLES // 2, int(lim * (1.0, 0.6, 0.3)[level]))

    def room(self, n=1, priority=False):
        cap = S.MAX_PARTICLES if priority else self.limit
        return len(self.items) + n <= cap

    @property
    def density(self):
        return self.limit / float(S.MAX_PARTICLES)

    def clear(self):
        self.items = []

    def update(self, dt):
        self.items = [p for p in self.items if p.update(dt)]

    def draw(self, surf):
        for p in self.items:
            p.draw(surf)

    # ---- efeitos de alto nível -----------------
    def explosion(self, x, y, size, flash, ring, palette, priority=False):
        if self.room(3, priority):
            # Anéis de choque duplos com estilo tecnológico
            self.items.append(Ring(x, y, size * 0.20, size * 1.10, ring, 0.38, width=4))
            self.items.append(Ring(x, y, size * 0.25, size * 0.85, flash, 0.20, width=2))
            self.items.append(Ring(x, y, size * 0.10, size * 0.50, "#ffffff", 0.12, filled=True))
        n = min(int(8 + size / 5), 18)
        if not priority:
            n = max(3, int(n * self.density))
        for _ in range(n):
            if not self.room(1, priority):
                break
            a = random.uniform(0, math.tau)
            sp = random.uniform(90, 140 + size * 2.8)
            self.items.append(Debris(x, y, math.cos(a) * sp, math.sin(a) * sp - 45,
                                      random.uniform(3, 7), random.choice(palette), random.uniform(0.4, 0.8)))

    def blast(self, x, y, radius):
        if self.room(3, True):
            self.items.append(Ring(x, y, radius * 0.2, radius * 1.2, "#00f0ff", 0.45, width=5))
            self.items.append(Ring(x, y, radius * 0.15, radius * 0.9, "#ff8a1f", 0.22, width=3))
            self.items.append(Ring(x, y, radius * 0.05, radius * 0.5, "#ffffff", 0.14, filled=True))
        for _ in range(int(10 * max(0.5, self.density))):
            if not self.room(1, True):
                break
            a = random.uniform(0, math.tau)
            sp = random.uniform(130, 140 + radius * 2.4)
            self.items.append(Debris(x, y, math.cos(a) * sp, math.sin(a) * sp - 55, random.uniform(3, 7),
                                      random.choice(("#00f0ff", "#ff8a1f", "#ffd23f", "#ffffff")), random.uniform(0.35, 0.65)))

    def impact(self, x, y, color):
        if self.level < 2 and self.room(1):
            self.items.append(Ring(x, y, 4, 16, color, 0.16, width=2))
        for _ in range(4 if self.level == 0 else 2):
            if self.room():
                a = random.uniform(math.pi, math.tau)
                sp = random.uniform(90, 220)
                self.items.append(Debris(x, y, math.cos(a) * sp, math.sin(a) * sp, 3.5, color, 0.3, 320))

    def dust(self, x, y, n=6):
        if self.level >= 2:
            return
        for _ in range(n):
            if self.room():
                d = random.choice((-1, 1))
                self.items.append(Debris(x + random.uniform(-10, 10), y - 2, d * random.uniform(50, 160),
                                          -random.uniform(15, 100), random.uniform(3, 6), "#7cecff",
                                          random.uniform(0.3, 0.5), 280))

    def sparks(self, x, y, color, n=4, up=True):
        if self.level >= 2:
            n = min(n, 1)
        for _ in range(n):
            if self.room():
                a = random.uniform(-2.8, -0.4) if up else random.uniform(-3.14, 0.0)
                sp = random.uniform(100, 280)
                self.items.append(Debris(x, y, math.cos(a) * sp, math.sin(a) * sp, random.uniform(2, 4.5),
                                          color, random.uniform(0.18, 0.4), 540))

    def casing(self, x, y, d):
        if self.level == 0 and self.room():
            self.items.append(Debris(x, y, d * random.uniform(80, 160), -random.uniform(130, 240), 3,
                                      "#ffe14d", 0.45, 920))

    def dash_trail(self, p):
        col = p.color
        if self.room(1):
            self.items.append(Ghost(p.x, p.y, col, 0.32))
        for _ in range(3 if self.level == 0 else 1):
            if self.room():
                self.items.append(Streak(p.x - p.dash_dir * random.uniform(12, 35), p.y - random.uniform(10, 58),
                                          -p.dash_dir * random.uniform(35, 80), col, 0.18))

    def popup(self, x, y, text, color, size=22):
        if self.room(1, True):
            self.items.append(FloatText(x, y, text, color, size))

    def ring(self, x, y, r0, r1, color, life=0.5, width=3):
        if self.room(1):
            self.items.append(Ring(x, y, r0, r1, color, life, width=width))