"""utils.py — funções utilitárias pequenas, portadas de main.py sem alterações de comportamento."""
import math

import pygame


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def approach(cur, target, step):
    if cur < target:
        return min(target, cur + step)
    return max(target, cur - step)


def overlap(a, b):
    """a, b: (x0, y0, x1, y1). True se os retângulos se sobrepõem."""
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def circle_hits_rect(cx, cy, r, rect):
    x0, y0, x1, y1 = rect
    nx = max(x0, min(cx, x1))
    ny = max(y0, min(cy, y1))
    return (cx - nx) ** 2 + (cy - ny) ** 2 <= r * r


def mult_clamp(factors, limits):
    """Multiplica uma lista de fatores e trava o resultado em [lo, hi]."""
    result = 1.0
    for f in factors:
        result *= f
    lo, hi = limits
    return clamp(result, lo, hi)


def ease_out(t):
    return 1 - (1 - t) * (1 - t)


def dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


_glow_cache = {}


def draw_glow_circle(surf, x, y, radius, color, intensity=1.0, layers=3):
    """Desenha um halo de luz néon suave (vários círculos translúcidos
    decrescentes) por trás de um ponto — usado para luzes de inimigos,
    pickups brilhando antes de expirar, etc. `intensity` em [0, 1] escala a
    opacidade (para pulsar).

    Desempenho: a superfície de cada (radius, color, layers) é desenhada
    UMA VEZ e cacheada (pygame.SRCALPHA, sem per-pixel alpha na superfície
    em si — a opacidade "base" já está embutida nos círculos). A variação
    de intensidade por quadro usa Surface.set_alpha(), que é uma operação O(1)
    (só seta um byte de estado), NUNCA Surface.copy() + BLEND_RGBA_MULT, que
    aloca e processa a superfície inteira a cada chamada — isso sozinho
    custava a maior parte do tempo de desenho em cenas com muitos inimigos."""
    radius = max(2, int(radius))
    key = (radius, color, layers)
    glow = _glow_cache.get(key)
    if glow is None:
        size = radius * 2
        glow = pygame.Surface((size, size), pygame.SRCALPHA)
        for i in range(layers, 0, -1):
            r = int(radius * i / layers)
            a = int(70 / i)
            pygame.draw.circle(glow, (*color, a), (radius, radius), r)
        _glow_cache[key] = glow
    glow.set_alpha(int(255 * clamp(intensity, 0.0, 1.0)))
    surf.blit(glow, (int(x - radius), int(y - radius)))


def pulse(t, speed=4.0, lo=0.5, hi=1.0):
    """Valor que oscila suavemente entre lo e hi — usado para luzes 'respirando'."""
    k = 0.5 + 0.5 * math.sin(t * speed)
    return lo + (hi - lo) * k


_font_cache = {}


def get_font(name, size, bold=False):
    """pygame.font.SysFont(...) cacheado por (nome, tamanho, bold). Criar uma
    SysFont busca a fonte no sistema operacional a cada chamada — caro o
    bastante para que recriá-la todo quadro (como em qualquer draw() chamado
    por frame: HUD, barra de vida de chefe, etc.) seja um gargalo real de
    desempenho. Sempre usar este helper em vez de pygame.font.SysFont direto
    em qualquer código que roda durante o gameplay (fora de telas de menu,
    onde o custo de poucas chamadas por transição de tela é desprezível)."""
    key = (name, size, bold)
    font = _font_cache.get(key)
    if font is None:
        import pygame
        font = pygame.font.SysFont(name, size, bold=bold)
        _font_cache[key] = font
    return font
