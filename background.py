"""
background.py — cenário de fundo "cidade cibernética" (cyberpunk), usado por
Game._draw_background(). Camadas, da mais distante para a mais próxima:

  1. céu em gradiente com poluição luminosa perto do horizonte
  2. feixes de luz cônicos cruzando o céu (holofotes/antenas)
  3. silhueta de arranha-céus distantes (mais escuros, mais lentos)
  4. silhueta de arranha-céus próximos (mais claros, janelas de néon
     piscando em azul/rosa/roxo, parallax mais rápido)
  5. linha de perigo + chão com grade de perspectiva (synthwave)

PERFORMANCE: tudo que não muda quadro a quadro (céu, feixes, grade, o
"corpo" de cada prédio) é desenhado UMA VEZ em superfícies pré-renderizadas
no __init__/quando a cidade rola o suficiente para precisar de um novo
recorte, e só colado (blit) depois — nunca recriado com pygame.Surface()
ou pygame.draw em loop a cada quadro. Só as janelas acesas (poucos pontos
de 2x2px, desenhados direto com pygame.draw.rect, sem Surface própria) e o
leve deslocamento de scroll mudam por quadro. Isso é o que mantém o fundo
dentro do orçamento de quadro mesmo em hardware modesto.
"""
import math
import random

import pygame

import settings as S

# Paleta industrial sci-fi: aço grafite, ciano de sensores e âmbar de alerta.
SKY_TOP = (5, 9, 18)
SKY_HORIZON = (19, 31, 45)
GLOW_COLOR = (32, 108, 132)
NEON_COLORS = ((65, 205, 230), (255, 176, 74), (122, 155, 190), (76, 225, 180))
GRID_COLOR = (45, 166, 190)
BEAM_COLOR = (95, 174, 204)

# só uma fração das janelas de um prédio pisca a cada quadro — dá a
# impressão de uma cidade "viva" sem recalcular centenas de senoides/quadro
WINDOW_REFRESH_FRACTION = 0.12


class _Building:
    __slots__ = ("x", "w", "h", "top", "color", "windows", "parallax", "lit", "blink_t")

    def __init__(self, x, w, h, top, color, parallax, rng):
        self.x, self.w, self.h, self.top = x, w, h, top
        self.color = color
        self.parallax = parallax
        self.windows = []    # cada item: [wx, wy, cor, aceso(bool), próxima_troca]
        cols = max(2, int(w // 14))
        rows = max(2, int(h // 18))
        for cy in range(rows):
            for cx in range(cols):
                if rng.random() < 0.55:
                    wx = x + 6 + cx * (w - 12) / max(1, cols - 1) if cols > 1 else x + w / 2
                    wy = top + 10 + cy * (h - 20) / max(1, rows - 1) if rows > 1 else top + h / 2
                    lit = rng.random() < 0.6
                    self.windows.append([wx, wy, rng.choice(NEON_COLORS), lit, rng.uniform(1.0, 4.0)])


class CityBackground:
    def __init__(self, width=S.WIDTH, horizon=S.DANGER_Y, seed=20260101):
        self.width = width
        # DANGER_Y marca o limite vertical de aproximação das naves.
        # GROUND_Y é o chão real onde o jogador fica: os prédios chegam até ele.
        self.horizon = int(horizon)
        self.ground_y = int(S.GROUND_Y)
        if self.ground_y <= self.horizon:
            raise ValueError("S.GROUND_Y deve ser maior que S.DANGER_Y")
        self.t = 0.0
        rng = random.Random(seed)   # seed fixa: skyline sempre igual entre partidas

        self.far = self._make_skyline(rng, count=14, y_top=horizon * 0.18, y_bottom=horizon * 0.62,
                                       h_range=(60, 170), w_range=(50, 110), color=(15, 25, 39), parallax=0.12)
        self.near = self._make_skyline(rng, count=10, y_top=horizon * 0.05, y_bottom=horizon * 0.78,
                                        h_range=(140, 320), w_range=(70, 150), color=(23, 35, 49), parallax=0.30)

        self.beam_defs = [dict(x=rng.uniform(0, width), angle=rng.uniform(-0.35, 0.35),
                                speed=rng.uniform(0.012, 0.035), phase=rng.uniform(0, math.tau)) for _ in range(3)]

        self.vanish = (width / 2, horizon - 6)
        self.grid_cols = 14

        # --- pré-renderização: tudo estático vira UMA superfície, desenhada uma única vez.
        self._sky = self._render_sky()
        self._far_body = self._render_skyline_bodies(self.far)
        self._near_body = self._render_skyline_bodies(self.near)
        self._grid = self._render_grid()
        self._beams_surf = self._render_beams_base()

    # ------------------------------------------------------------ construção do skyline (dados)
    def _make_skyline(self, rng, count, y_top, y_bottom, h_range, w_range, color, parallax):
        buildings = []
        x = -40.0
        while x < self.width + 40:
            w = rng.uniform(*w_range)
            roof_offset = rng.uniform(*h_range)
            # Mantém a altura visual dos telhados em relação ao limite de perigo,
            # mas prolonga cada edifício até o chão onde o jogador se movimenta.
            top = max(10.0, self.horizon - roof_offset)
            building_height = max(12.0, self.ground_y - top)
            shade = rng.uniform(0.85, 1.18)
            col = tuple(min(255, max(0, int(c * shade))) for c in color)
            buildings.append(_Building(x, w, building_height, top, col, parallax, rng))
            x += w * rng.uniform(0.55, 0.85)
        return buildings

    # ------------------------------------------------------------ pré-renderização (uma vez)
    def _render_sky(self):
        sky = pygame.Surface((self.width, self.horizon))
        steps = 18
        h = self.horizon
        for i in range(steps):
            t0, t1 = i / steps, (i + 1) / steps
            col = _lerp_color(SKY_TOP, SKY_HORIZON, t0 ** 1.6)
            pygame.draw.rect(sky, col, (0, int(t0 * h), self.width, int((t1 - t0) * h) + 1))
        glow_h = int(h * 0.22)
        for i in range(glow_h):
            a = i / glow_h
            col = _lerp_color(sky.get_at((0, h - glow_h + i))[:3], GLOW_COLOR, 0.28 * (1.0 - a))
            pygame.draw.line(sky, col, (0, h - glow_h + i), (self.width, h - glow_h + i))
        return sky

    def _render_skyline_bodies(self, buildings):
        """Desenha só o CORPO (retângulos) dos prédios numa tira larga o
        bastante para o scroll dar a volta sem costura visível; as janelas
        acesas são desenhadas por cima, por quadro, direto na tela (ver
        _draw_skyline) porque elas mudam — mas o corpo nunca muda."""
        tile_w = self.width + 80
        # A tira vai até GROUND_Y, não apenas até DANGER_Y.
        body = pygame.Surface((tile_w, self.ground_y), pygame.SRCALPHA)
        for b in buildings:
            sx = b.x + 40
            bx, by, bw = int(sx), int(b.top), max(8, int(b.w))
            # Todos os prédios tocam o chão real do jogador.
            by = max(0, min(by, self.ground_y - 12))
            bh = self.ground_y - by
            # Corpo principal e topo de manutenção em níveis, como prédios-fábrica.
            pygame.draw.rect(body, b.color, (bx, by, bw, bh))
            top_col = tuple(min(255, int(c * 1.28 + 5)) for c in b.color)
            shadow_col = tuple(max(0, int(c * 0.55)) for c in b.color)
            pygame.draw.rect(body, top_col, (bx, by, bw, 3))
            pygame.draw.rect(body, shadow_col, (bx + bw - 4, by + 3, 4, bh - 3))
            pygame.draw.rect(body, shadow_col, (bx + int(bw * 0.35), by - 10, max(3, int(bw * 0.3)), 10))
            # Frisos estruturais, grelhas de ventilação e antena em alguns edifícios.
            for fy in range(by + 18, by + bh - 8, 28):
                pygame.draw.line(body, shadow_col, (bx + 4, fy), (bx + bw - 7, fy), 1)
            if bw > 82:
                vent = pygame.Rect(bx + 8, by + 8, min(22, bw // 4), 7)
                pygame.draw.rect(body, shadow_col, vent)
                for vx in range(vent.left + 3, vent.right - 1, 4):
                    pygame.draw.line(body, top_col, (vx, vent.top + 1), (vx, vent.bottom - 1), 1)
            if int(b.x) % 3 == 0:
                ax = bx + bw // 2
                pygame.draw.line(body, shadow_col, (ax, by - 10), (ax, by - 23), 2)
                pygame.draw.circle(body, (*NEON_COLORS[0], 170), (ax, max(1, by - 24)), 2)
        return body

    def _render_grid(self):
        floor_y = S.GROUND_Y
        grid_h = floor_y - self.horizon
        grid = pygame.Surface((self.width, grid_h), pygame.SRCALPHA)
        vx, _ = self.vanish
        n = self.grid_cols
        for i in range(-n, n + 1):
            bx = vx + i * (self.width * 2.2 / n)
            pygame.draw.line(grid, (*GRID_COLOR, 45), (vx, 0), (bx, grid_h), 1)
        rows = 10
        for j in range(rows + 1):
            ty = (j / rows) ** 1.6 * grid_h   # linhas mais próximas do jogador, mais espaçadas (perspectiva)
            a = int(20 + 70 * (ty / max(1, grid_h)))
            pygame.draw.line(grid, (*GRID_COLOR, a), (0, int(ty)), (self.width, int(ty)), 1)
        return grid

    def _render_beams_base(self):
        """Um feixe 'canônico' (vertical, no x=0) pré-renderizado uma vez;
        por quadro só giramos/posicionamos com blit, nunca recriamos a surface."""
        length = int(self.horizon * 0.9) + 2
        beam = pygame.Surface((80, length), pygame.SRCALPHA)
        pygame.draw.polygon(beam, (*BEAM_COLOR, 10), [(40, 0), (14, length), (66, length)])
        pygame.draw.line(beam, (*BEAM_COLOR, 22), (40, 0), (40, length), 1)
        return beam

    # ------------------------------------------------------------ atualização
    def update(self, dt):
        self.t += dt
        # alterna um punhado de janelas por quadro (não todas, não com custo de
        # senoide por janela): cada janela tem seu próprio relógio de troca.
        for layer in (self.far, self.near):
            for b in layer:
                for win in b.windows:
                    win[4] -= dt
                    if win[4] <= 0:
                        win[3] = not win[3] if random.random() < 0.7 else win[3]
                        win[4] = random.uniform(1.0, 4.0)

    # ------------------------------------------------------------ desenho
    def draw(self, surf):
        surf.blit(self._sky, (0, 0))
        # Preenche o trecho entre o limite das naves e o chão atrás da cidade.
        # Os prédios são desenhados depois e descem até GROUND_Y.
        pygame.draw.rect(
            surf, (7, 13, 23),
            (0, self.horizon, self.width, self.ground_y - self.horizon)
        )
        self._draw_beams(surf)
        self._draw_skyline(surf, self.far, self._far_body)
        self._draw_skyline(surf, self.near, self._near_body)
        self._draw_ground(surf)

    def _draw_beams(self, surf):
        for b in self.beam_defs:
            sway = math.sin(self.t * b["speed"] * math.tau + b["phase"]) * 40
            bx = b["x"] + sway - 40
            surf.blit(self._beams_surf, (int(bx), 0))

    def _draw_skyline(self, surf, buildings, body_surf):
        scroll = -(self.t * 6.0)
        parallax = buildings[0].parallax if buildings else 0.0
        tile_w = self.width + 80
        offset = int((scroll * parallax) % tile_w)
        # a tira pré-renderizada é colada 1 ou 2 vezes (deslocada) para cobrir a
        # largura da tela sem costura, continuando o scroll horizontal.
        surf.blit(body_surf, (offset - 40, 0))
        if offset > 40:
            surf.blit(body_surf, (offset - 40 - tile_w, 0))

        for b in buildings:
            sx = ((b.x + scroll * b.parallax) % tile_w) - 40
            for wx, wy, col, lit, _ in b.windows:
                if not lit:
                    continue
                wxs = sx + (wx - b.x)
                if -4 <= wxs <= self.width + 4:
                    pygame.draw.rect(surf, col, (int(wxs), int(wy), 4, 4))

    def _draw_ground(self, surf):
        h = S.HEIGHT
        horizon = self.horizon
        ground_y = self.ground_y
        # A grade é translúcida e passa à frente da cidade; não apaga os prédios.
        scroll_y = int((self.t * 70.0) % 24)
        surf.blit(self._grid, (0, horizon + scroll_y - 24))
        surf.blit(self._grid, (0, horizon + scroll_y))

        # Limite máximo de aproximação das naves: linha pontilhada discreta,
        # sem a antiga divisória ciano contínua.
        dash_y = int(horizon)
        dash_width, dash_gap = 7, 8
        dash_color = (58, 112, 130)
        for tx in range(0, self.width, dash_width + dash_gap):
            x2 = min(tx + dash_width - 1, self.width - 1)
            pygame.draw.line(surf, dash_color, (tx, dash_y), (x2, dash_y), 1)

        pygame.draw.rect(surf, (10, 17, 27), (0, ground_y, self.width, h - ground_y))
        pygame.draw.line(surf, (43, 75, 89), (0, ground_y), (self.width, ground_y), 1)
        # Painéis de piso e pequenas luzes de sinalização.
        for tx in range(24, self.width, 160):
            pygame.draw.line(surf, (24, 51, 66), (tx, ground_y + 5), (tx + 70, ground_y + 5), 1)
            pygame.draw.rect(surf, (255, 176, 74), (tx, ground_y + 10, 5, 2))


def _lerp_color(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

