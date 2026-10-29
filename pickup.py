"""
pickup.py — item coletável que cai de um inimigo (porte de Pickup em main.py).
kind = 'boost' (positivo/negativo) ou 'weapon'. Cai até o chão; depois de
pousar fica disponível por PICKUP_LIFETIME (ou WEAPON_PICKUP_LIFETIME)
segundos de jogo e some. Coletado por colisão real, uma única vez.
"""
import math

import pygame

import settings as S
from utils import draw_glow_circle, clamp, pulse, get_font


class Pickup:
    R = 15

    def __init__(self, kind, key, x, y):
        self.kind, self.key = kind, key
        self.x, self.y = x, y
        self.landed = False
        self.age = 0.0
        self.life = S.PICKUP_LIFETIME if kind == "boost" else S.WEAPON_PICKUP_LIFETIME
        self.alive = True
        self.collected = False
        self.hb = self._hb()

    def _hb(self):
        return (self.x - 14, self.y - 14, self.x + 14, self.y + 14)

    @property
    def good(self):
        return self.kind == "weapon" or S.BOOSTS[self.key]["good"]

    def remaining(self):
        return max(0.0, self.life - self.age) if self.landed else self.life

    def update(self, dt):
        if not self.landed:
            self.y += S.PICKUP_FALL_SPEED * dt
            if self.y + self.R >= S.GROUND_Y:
                self.y = S.GROUND_Y - self.R
                self.landed = True
        else:
            self.age += dt
            if self.age >= self.life - 1e-9:
                self.alive = False
        self.hb = self._hb()

    def _blinking_hidden(self):
        """Pisca ao expirar, igual ao original (mantido: o piscar abrupto é o
        aviso mais legível de 'vai sumir', o glow crescente abaixo só reforça)."""
        return self.landed and self.remaining() < 0.9 and int(self.age * 12) % 2 == 1

    def _urgency(self):
        """0 → recém-caído; 1 → prestes a expirar. Usado para o halo crescer e
        pulsar mais rápido conforme o tempo acaba, dando um aviso visual
        gradual além do piscar binário dos últimos instantes."""
        if not self.landed:
            return 0.0
        warn_window = 2.2
        left = self.remaining()
        return clamp(1.0 - left / warn_window, 0.0, 1.0) if left < warn_window else 0.0

    # ------------------------------------------------------------ desenho
    def draw(self, surf, font):
        if self._blinking_hidden():
            return
        x, y, R = int(self.x), int(self.y), self.R
        urgency = self._urgency()
        pulse_speed = 3.0 + urgency * 9.0     # pulsa cada vez mais rápido perto de expirar
        glow_scale = 1.0 + urgency * 0.6       # e o halo cresce um pouco

        if self.kind == "weapon":
            self._draw_weapon(surf, font, x, y, glow_scale, pulse_speed)
        else:
            self._draw_boost(surf, font, x, y, R, glow_scale, pulse_speed)

    @staticmethod
    def _mix_color(color, target, amount):
        """Mistura duas cores sem depender de configurações externas."""
        return tuple(
            max(0, min(255, round(color[i] * (1 - amount) + target[i] * amount)))
            for i in range(3)
        )

    @staticmethod
    def _darken(color, factor=0.35):
        return tuple(max(0, min(255, round(channel * factor))) for channel in color)

    @staticmethod
    def _lighten(color, amount=0.58):
        return Pickup._mix_color(color, (255, 255, 255), amount)

    def _draw_weapon(self, surf, font, x, y, glow_scale, pulse_speed):
        w = S.WEAPONS[self.key]
        base = S.hx(w["color"]) if w["color"] else (255, 220, 120)
        col = self._lighten(base, 0.42)
        dark = self._darken(base, 0.24)
        highlight = self._lighten(base, 0.78)

        glow_r = 29 * glow_scale
        draw_glow_circle(
            surf, x, y, glow_r, col,
            intensity=pulse(self.age, pulse_speed, 0.48, 0.92), layers=4
        )

        # Cápsula metálica com núcleo claro e bordas de alto contraste.
        box = pygame.Rect(0, 0, 38, 32)
        box.center = (x, y)
        pygame.draw.rect(surf, (7, 15, 24), box, border_radius=7)
        pygame.draw.rect(surf, dark, box, width=3, border_radius=7)
        inner = box.inflate(-6, -6)
        pygame.draw.rect(surf, self._darken(base, 0.52), inner, border_radius=4)
        core = inner.inflate(-8, -7)
        pygame.draw.rect(surf, col, core, border_radius=3)
        pygame.draw.line(surf, highlight, (box.left + 7, box.top + 4),
                         (box.right - 8, box.top + 4), 2)
        pygame.draw.line(surf, highlight, (box.left + 5, box.bottom - 4),
                         (box.left + 11, box.bottom - 4), 1)

        label = font.render(w["name"][0].upper(), True, (255, 255, 255))
        surf.blit(label, label.get_rect(center=(x, y)))
        tag_font = get_font(S.FONT_UI_NAME, 10, bold=True)
        tag = tag_font.render("ARMA", True, highlight)
        surf.blit(tag, tag.get_rect(midtop=(x, box.bottom + 2)))

    def _draw_boost(self, surf, font, x, y, R, glow_scale, pulse_speed):
        b = S.BOOSTS[self.key]
        base = S.hx(b["color"])
        good = bool(b["good"])

        # Itens positivos: tons claros, núcleo luminoso e halo mais limpo.
        # Itens negativos: tons escuros, borda vinho/âmbar e brilho contido.
        if good:
            col = self._lighten(base, 0.58)
            edge = self._lighten(base, 0.76)
            core = self._lighten(base, 0.82)
            body = self._mix_color(base, (10, 25, 38), 0.42)
            glow_intensity = pulse(self.age, pulse_speed, 0.52, 1.0)
        else:
            col = self._darken(base, 0.58)
            edge = self._darken(base, 0.42)
            core = self._darken(base, 0.32)
            body = (12, 10, 19)
            glow_intensity = pulse(self.age, pulse_speed, 0.18, 0.48)

        glow_r = (R + (17 if good else 11)) * glow_scale
        draw_glow_circle(
            surf, x, y, glow_r, col,
            intensity=glow_intensity, layers=4 if good else 2
        )

        if good:
            # Silhueta circular: leitura rápida de benefício.
            pygame.draw.circle(surf, (5, 17, 27), (x, y), R + 2)
            pygame.draw.circle(surf, edge, (x, y), R + 1, width=2)
            pygame.draw.circle(surf, body, (x, y), R - 2)
            pygame.draw.circle(surf, col, (x, y), R - 5, width=2)
            pygame.draw.arc(
                surf, core, pygame.Rect(x - R + 4, y - R + 4, (R - 4) * 2, (R - 4) * 2),
                math.radians(205), math.radians(325), 2
            )
            # Pequeno brilho especular no topo.
            pygame.draw.line(surf, core, (x - 5, y - R + 5), (x + 3, y - R + 5), 2)
        else:
            # Hexágono escuro e facetado: indica perigo sem depender só da cor.
            def hexa(r):
                return [
                    (round(x + r * math.cos(a * math.pi / 3 + math.pi / 6)),
                     round(y + r * math.sin(a * math.pi / 3 + math.pi / 6)))
                    for a in range(6)
                ]

            outer = hexa(R + 2)
            inner = hexa(R - 2)
            pygame.draw.polygon(surf, (5, 5, 12), outer)
            pygame.draw.polygon(surf, edge, outer, width=2)
            pygame.draw.polygon(surf, body, inner)
            pygame.draw.line(surf, core, (x - 6, y - 5), (x + 5, y - 5), 1)
            pygame.draw.line(surf, edge, (x - 7, y + 5), (x + 6, y + 5), 1)

        # Ícone claro nos dois tipos para manter a leitura sobre o corpo escuro.
        icon_color = (255, 255, 255) if good else (205, 196, 210)
        label = font.render(b["icon"], True, icon_color)
        shadow = font.render(b["icon"], True, (0, 0, 0))
        surf.blit(shadow, shadow.get_rect(center=(x + 1, y + 2)))
        surf.blit(label, label.get_rect(center=(x, y)))
