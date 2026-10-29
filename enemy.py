"""
enemy.py — inimigos padrão (drone, nave, máquina), chefes (Miniboss,
Mothership, FinalBoss) e encontros especiais (CyberCar, Jet).

Porte fiel da lógica de main.py (classes Enemy em diante). O desenho usa
formas simples do pygame.draw em vez dos sprites poligonais detalhados do
Canvas original (que tinham dezenas de pontos por inimigo) — a hitbox, vida,
pontuação, IA e padrões de ataque são idênticos ao original.
"""
import math
import random

import pygame

import settings as S
from utils import clamp, ease_out, draw_glow_circle, pulse, get_font

HIDDEN_HB = (-9999.0, -9999.0, -9990.0, -9990.0)


class Enemy:
    """Classe base. slot_x/slot_y = posição "oficial" da formação; x/y = posição
    final renderizada (= slot + oscilação própria - deslocamento de entrada)."""
    solo = False
    breachable = True
    shootable = True
    contact_damage = True
    is_boss = False

    def __init__(self, squad, kind, x, y, hp, phase):
        cfg = S.ENEMY_TYPES[kind]
        self.squad, self.kind, self.cfg = squad, kind, cfg
        self.w, self.h = cfg["w"], cfg["h"]
        self.sc = cfg.get("sprite_scale", 1.0)
        self.flip = 1
        self.points = cfg["points"]
        self.max_hp = self.hp = hp
        self.slot_x, self.slot_y = x, y
        self.entry = S.ENTRY_DROP
        self.phase = phase
        self.t = random.uniform(0, 10)
        self.flash = 0.0
        self.alive = True
        self.x, self.y = x, y - self.entry
        self.hb = self._calc_hb()

    def _calc_hb(self):
        hw, hh = self.cfg["hit_w"] / 2, self.cfg["hit_h"] / 2
        return (self.x - hw, self.y - hh, self.x + hw, self.y + hh)

    def wobble(self):
        return 0.0, 0.0

    def update(self, dt):
        self.t += dt
        if self.flash > 0:
            self.flash -= dt
        ox, oy = self.wobble()
        self.x = self.slot_x + ox
        self.y = self.slot_y - self.entry + oy
        self.hb = self._calc_hb()

    def hitbox(self):
        return self.hb

    def hit(self, dmg=S.SHOT_DAMAGE):
        if not self.alive:
            return False
        self.hp -= dmg
        self.flash = 0.08
        if self.hp <= 1e-9:
            self.alive = False
            return True
        return False

    def on_destroyed(self, game):
        pass

    # ---------------------------------------------------------- desenho
    def _color(self):
        return S.hx(self.cfg["fx"][1])

    def _neon_color(self):
        """Cor de destaque (néon) do inimigo: a terceira entrada de cfg['fx'],
        usada para o contorno luminoso e o halo por trás do corpo."""
        fx = self.cfg["fx"][2]
        return S.hx(fx[0] if fx else self.cfg["fx"][0])

    def draw(self, surf):
        """Renderização mecânica detalhada; mantém hitbox e lógica originais."""
        col = (255, 255, 255) if self.flash > 0 else self._color()
        neon = self._neon_color()
        x, y = int(self.x), int(self.y)
        w, h = max(24, int(self.w)), max(20, int(self.h))
        glow_r = max(w, h) * (0.48 if self.is_boss else 0.38)
        draw_glow_circle(surf, x, y, glow_r, neon,
                         intensity=pulse(self.t, speed=2.4, lo=0.18, hi=0.42),
                         layers=2)

        dark = S.hx("#111522")
        shadow = S.hx("#252d3d")
        steel = S.hx("#596779")
        light = S.hx("#aab8c8")
        black = S.hx("#080b12")
        cyan = S.hx("#7cecff")
        red = S.hx("#ff684f")

        def poly(points, color, outline=black, width=2):
            pts = [(int(px), int(py)) for px, py in points]
            pygame.draw.polygon(surf, color, pts)
            if outline:
                pygame.draw.polygon(surf, outline, pts, width)

        def line(points, color, width=2):
            pygame.draw.lines(surf, color, False,
                              [(int(px), int(py)) for px, py in points], width)

        def panel(cx, cy, pw, ph, fill=shadow, border=black, radius=3):
            r = pygame.Rect(int(cx-pw/2), int(cy-ph/2), int(pw), int(ph))
            pygame.draw.rect(surf, fill, r, border_radius=radius)
            pygame.draw.rect(surf, border, r, 2, border_radius=radius)
            pygame.draw.line(surf, light, (r.left+3, r.top+2), (r.right-4, r.top+2), 1)

        # Silhueta distinta por classe: metal em camadas, juntas e componentes.
        kind = self.kind
        if kind == "drone":
            # Drone de reconhecimento: braços articulados e rotor protegido.
            poly([(x-w*.48,y-h*.08),(x-w*.34,y-h*.36),(x-w*.12,y-h*.43),
                  (x+w*.12,y-h*.43),(x+w*.34,y-h*.36),(x+w*.48,y-h*.08),
                  (x+w*.34,y+h*.28),(x+w*.15,y+h*.39),(x-w*.15,y+h*.39),
                  (x-w*.34,y+h*.28)], steel)
            poly([(x-w*.27,y-h*.12),(x-w*.16,y-h*.30),(x+w*.16,y-h*.30),
                  (x+w*.27,y-h*.12),(x+w*.19,y+h*.18),(x-w*.19,y+h*.18)], shadow)
            for side in (-1,1):
                sx=x+side*w*.39
                line([(x+side*w*.17,y-h*.22),(sx,y-h*.34),(sx+side*w*.08,y-h*.20)], light, 3)
                pygame.draw.ellipse(surf, dark, (int(sx-w*.12),int(y-h*.43),int(w*.24),int(h*.20)))
                pygame.draw.ellipse(surf, neon, (int(sx-w*.07),int(y-h*.39),int(w*.14),int(h*.10)))
            panel(x,y+h*.23,w*.28,h*.13,dark)
            line([(x-w*.12,y-h*.18),(x-w*.05,y-h*.25),(x+w*.08,y-h*.25)], light, 2)

        elif kind in ("ship", "mini"):
            # Caça compacto com asas, cockpit blindado e motores traseiros.
            poly([(x,y-h*.48),(x+w*.15,y-h*.10),(x+w*.48,y+h*.22),
                  (x+w*.22,y+h*.19),(x+w*.13,y+h*.42),(x-w*.13,y+h*.42),
                  (x-w*.22,y+h*.19),(x-w*.48,y+h*.22),(x-w*.15,y-h*.10)], steel)
            poly([(x,y-h*.36),(x+w*.09,y-h*.04),(x+w*.08,y+h*.20),
                  (x-w*.08,y+h*.20),(x-w*.09,y-h*.04)], light)
            poly([(x,y-h*.28),(x+w*.055,y-h*.06),(x,y+h*.08),(x-w*.055,y-h*.06)], cyan, black, 1)
            for side in (-1,1):
                ex=x+side*w*.17
                pygame.draw.ellipse(surf, dark,(int(ex-w*.075),int(y+h*.25),int(w*.15),int(h*.20)))
                pygame.draw.ellipse(surf, neon,(int(ex-w*.04),int(y+h*.29),int(w*.08),int(h*.12)))
                line([(x+side*w*.13,y),(x+side*w*.37,y+h*.15)], light, 2)
            line([(x-w*.25,y+h*.22),(x-w*.12,y+h*.27),(x+w*.12,y+h*.27),(x+w*.25,y+h*.22)], black, 2)

        elif kind == "machine":
            # Unidade de assalto: blindagem pesada e núcleo de energia.
            poly([(x-w*.31,y-h*.35),(x-w*.12,y-h*.48),(x+w*.12,y-h*.48),
                  (x+w*.31,y-h*.35),(x+w*.43,y+h*.10),(x+w*.28,y+h*.38),
                  (x-w*.28,y+h*.38),(x-w*.43,y+h*.10)], steel)
            poly([(x-w*.24,y-h*.22),(x-w*.12,y-h*.35),(x+w*.12,y-h*.35),
                  (x+w*.24,y-h*.22),(x+w*.18,y+h*.20),(x-w*.18,y+h*.20)], shadow)
            for side in (-1,1):
                sx=x+side*w*.34
                panel(sx,y+h*.02,w*.20,h*.33,steel)
                pygame.draw.circle(surf, red, (int(sx),int(y-h*.02)), max(2,int(w*.035)))
                line([(x+side*w*.18,y+h*.23),(x+side*w*.28,y+h*.42)], light, 3)
            pygame.draw.circle(surf, dark,(x,y),max(5,int(min(w,h)*.19)))
            pygame.draw.circle(surf, neon,(x,y),max(3,int(min(w,h)*.12)),2)
            pygame.draw.circle(surf, S.hx("#fff0b0"),(x,y),max(2,int(min(w,h)*.055)))
            for yy in (-.25,-.12,.12):
                line([(x-w*.12,y+h*yy),(x+w*.12,y+h*yy)], light, 1)

        elif kind in ("miniboss", "mothership", "finalboss"):
            # Chassi de chefe com ombreiras, placas sobrepostas e núcleo central.
            scale = 1.0 if kind == "miniboss" else 1.18
            poly([(x-w*.48,y-h*.05),(x-w*.39,y-h*.34),(x-w*.18,y-h*.43),
                  (x+w*.18,y-h*.43),(x+w*.39,y-h*.34),(x+w*.48,y-h*.05),
                  (x+w*.36,y+h*.32),(x+w*.18,y+h*.43),(x-w*.18,y+h*.43),
                  (x-w*.36,y+h*.32)], steel)
            for side in (-1,1):
                poly([(x+side*w*.43,y-h*.20),(x+side*w*.50,y+h*.03),
                      (x+side*w*.39,y+h*.25),(x+side*w*.28,y+h*.12)], shadow)
                line([(x+side*w*.42,y-h*.12),(x+side*w*.36,y+h*.08)], neon, 2)
                for j in range(2):
                    pygame.draw.circle(surf, red if kind=="finalboss" else neon,
                                       (int(x+side*w*(.34-j*.06)),int(y+h*(.19+j*.08))),
                                       max(2,int(w*.025)))
            poly([(x-w*.23,y-h*.20),(x-w*.14,y-h*.32),(x+w*.14,y-h*.32),
                  (x+w*.23,y-h*.20),(x+w*.17,y+h*.20),(x,y+h*.29),
                  (x-w*.17,y+h*.20)], dark)
            poly([(x,y-h*.25),(x+w*.10,y-h*.04),(x,y+h*.17),(x-w*.10,y-h*.04)], neon, black, 2)
            pygame.draw.circle(surf, S.hx("#f5fbff"),(x,y-h*.04),max(2,int(w*.035)))
            for side in (-1,1):
                panel(x+side*w*.20,y+h*.02,w*.11,h*.23,light)
            line([(x-w*.22,y+h*.27),(x-w*.10,y+h*.34),(x+w*.10,y+h*.34),(x+w*.22,y+h*.27)], light, 2)
            if kind == "finalboss":
                pygame.draw.ellipse(surf, neon, (int(x-w*.27),int(y-h*.48),int(w*.54),int(h*.96)), 2)

        elif kind == "car":
            # Carro de combate: chassis baixo, rodas, para-choques e cockpit.
            poly([(x-w*.48,y+h*.08),(x-w*.38,y-h*.16),(x-w*.20,y-h*.30),
                  (x+w*.20,y-h*.30),(x+w*.38,y-h*.16),(x+w*.48,y+h*.08),
                  (x+w*.43,y+h*.28),(x-w*.43,y+h*.28)], steel)
            poly([(x-w*.22,y-h*.24),(x-w*.13,y-h*.38),(x+w*.13,y-h*.38),
                  (x+w*.22,y-h*.24)], light)
            poly([(x-w*.13,y-h*.31),(x-w*.08,y-h*.22),(x+w*.08,y-h*.22),
                  (x+w*.13,y-h*.31)], cyan, black, 1)
            for side in (-1,1):
                wx=x+side*w*.30
                pygame.draw.rect(surf, black,(int(wx-w*.09),int(y+h*.13),int(w*.18),int(h*.25)),border_radius=3)
                pygame.draw.line(surf, light,(int(wx-w*.05),int(y+h*.16)),(int(wx+w*.05),int(y+h*.30)),2)
            line([(x-w*.35,y+h*.12),(x+w*.35,y+h*.12)], neon, 3)
            panel(x,y+h*.04,w*.22,h*.10,dark)

        elif kind == "jet":
            # Jato de ataque com asas varridas, cockpit e motores traseiros.
            poly([(x,y-h*.48),(x+w*.12,y-h*.08),(x+w*.48,y+h*.24),
                  (x+w*.24,y+h*.18),(x+w*.12,y+h*.40),(x-w*.12,y+h*.40),
                  (x-w*.24,y+h*.18),(x-w*.48,y+h*.24),(x-w*.12,y-h*.08)], steel)
            poly([(x,y-h*.35),(x+w*.06,y-h*.05),(x+w*.045,y+h*.13),
                  (x-w*.045,y+h*.13),(x-w*.06,y-h*.05)], cyan, black, 1)
            for side in (-1,1):
                ex=x+side*w*.16
                pygame.draw.ellipse(surf, black,(int(ex-w*.055),int(y+h*.25),int(w*.11),int(h*.17)))
                pygame.draw.ellipse(surf, neon,(int(ex-w*.03),int(y+h*.29),int(w*.06),int(h*.09)))
                line([(x+side*w*.10,y+h*.05),(x+side*w*.37,y+h*.20)], light, 2)
            line([(x-w*.20,y-h*.01),(x,y+h*.10),(x+w*.20,y-h*.01)], light, 2)

        else:
            pygame.draw.ellipse(surf, steel, (x-w//2,y-h//2,w,h))
            pygame.draw.ellipse(surf, black, (x-w//2,y-h//2,w,h), 3)

        # Rebites, marcas de manutenção e brilho de arestas.
        for side in (-1, 1):
            pygame.draw.circle(surf, light, (int(x+side*w*.28),int(y-h*.20)), 1)
        line([(x-w*.20,y-h*.31),(x-w*.10,y-h*.36),(x+w*.10,y-h*.36)], light, 1)

        self._draw_extra(surf)
        if self.max_hp >= 3 and self.shootable and self.hp < self.max_hp:
            self._draw_bar(surf)

    def _draw_extra(self, surf):
        pass

    def _draw_bar(self, surf):
        ratio = clamp(self.hp / self.max_hp, 0.0, 1.0)
        x0 = self.x - self.w / 2
        y0 = self.y - self.h / 2 - 12
        col = S.hx("#46f08a") if ratio > 0.5 else S.hx("#ffd23f") if ratio > 0.25 else S.hx("#ff4d4d")
        pygame.draw.rect(surf, S.hx("#12142a"), (x0, y0, self.w, 5), border_radius=2)
        pygame.draw.rect(surf, col, (x0 + 1, y0 + 1, (self.w - 2) * ratio, 3), border_radius=1)
        pygame.draw.rect(surf, col, (x0, y0, self.w, 5), width=1, border_radius=2)


# ---------------------------------------------------------------- inimigos padrão
class Drone(Enemy):
    def wobble(self):
        return 0.0, 3.0 * math.sin(self.t * 5 + self.phase)

    def _draw_extra(self, surf):
        x, y = int(self.x), int(self.y)
        neon = self._neon_color()
        pygame.draw.line(surf, S.hx("#d7def2"), (x - 18, y - 9), (x + 18, y - 9), 3)
        # "olho" central: núcleo sólido + halo pulsante, como uma lanterna de drone cyberpunk
        pulse_k = pulse(self.t, speed=6.0, lo=0.5, hi=1.0)
        draw_glow_circle(surf, x, y, 11, neon, intensity=pulse_k, layers=2)
        pygame.draw.circle(surf, S.hx("#fff35c"), (x, y), 4)
        pygame.draw.circle(surf, neon, (x, y), 4, width=1)


class Spaceship(Enemy):
    def wobble(self):
        return 0.0, 6.0 * math.sin(self.t * 2.6 + self.phase)

    def _draw_extra(self, surf):
        x, y = int(self.x), int(self.y)
        neon = self._neon_color()
        k = int(self.t * 3 + self.phase) % 3
        for i, lx in enumerate((-15, 0, 15)):
            lit = i == k
            col = S.hx("#ffe14d") if lit else S.hx("#2a1a60")
            if lit:
                draw_glow_circle(surf, x + lx, y + 5, 9, neon, intensity=0.85, layers=2)
            pygame.draw.circle(surf, col, (x + lx, y + 5), 3)
            pygame.draw.circle(surf, S.hx(S.OUTLINE), (x + lx, y + 5), 3, width=1)


class MiniShip(Spaceship):
    """Nave menor gerada pela nave-mãe: entra na lista de inimigos de verdade (colide, atira, pontua)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fire_t = random.uniform(*S.MINI_FIRE_INTERVAL)

    def update(self, dt):
        super().update(dt)
        w = self.squad.wave
        if w.state == "active":
            self.fire_t -= dt * w.game.enemy_attack_rate
            if self.fire_t <= 0:
                self.fire_t = random.uniform(*S.MINI_FIRE_INTERVAL)
                tgt = w.game.random_target()
                if tgt is not None:
                    w.game.aim_bullet(self.x, self.y + 14, tgt, S.MINI_BULLET_SPEED)


class FlyingMachine(Enemy):
    def wobble(self):
        return 0.0, 4.0 * math.sin(self.t * 1.6 + self.phase)

    def _draw_extra(self, surf):
        x, y = int(self.x), int(self.y)
        neon = self._neon_color()
        burst = self.squad.mode == "burst"
        core_col = S.hx("#ff5a36") if int(self.t * 4) % 2 == 0 else S.hx("#ff9d4d")
        draw_glow_circle(surf, x, y, 18, neon, intensity=pulse(self.t, speed=4.0, lo=0.4, hi=0.9), layers=3)
        pygame.draw.circle(surf, core_col, (x, y), 10)
        pygame.draw.circle(surf, S.hx(S.OUTLINE), (x, y), 10, width=2)
        if burst:
            for fx in (-26, 26):
                pygame.draw.polygon(surf, S.hx("#ff8a1f"),
                                     [(x + fx - 8, y + 26), (x + fx + 8, y + 26), (x + fx, y + 46)])


ENEMY_CLASSES = {"drone": Drone, "ship": Spaceship, "machine": FlyingMachine, "mini": MiniShip}


# ---------------------------------------------------------------- chefes
class Boss(Enemy):
    """Base dos chefes: entrada invulnerável, fila de ataques agendados (schedule),
    multiplicadores de boost atenuados (BOSS_EFFECT_SCALE), barra de vida."""
    solo = True
    breachable = False
    is_boss = True
    BAR_COLOR = "#ff4d4d"

    def __init__(self, wave, kind, x, y, hp):
        super().__init__(None, kind, x, y, hp, 0.0)
        self.wave, self.game = wave, wave.game
        self.cx, self.base_y = x, y
        self.intro = S.BOSS_INTRO_TIME
        self.invulnerable = True
        self.mt = 0.0
        self.queue = []
        self.y = -self.h / 2
        self.hb = self._calc_hb()

    def _scaled(self, m):
        return 1.0 + (m - 1.0) * S.BOSS_EFFECT_SCALE

    def mdt(self, dt):
        return dt * self._scaled(self.game.enemy_move_mult)

    def adt(self, dt):
        return dt * self._scaled(self.game.enemy_attack_rate)

    def schedule(self, delay, fn):
        self.queue.append([delay, fn])

    def _run_queue(self, dt):
        if not self.queue:
            return
        for item in self.queue:
            item[0] -= dt
        due = [it for it in self.queue if it[0] <= 0]
        if due:
            self.queue = [it for it in self.queue if it[0] > 0]
            for it in due:
                if self.alive:
                    it[1]()

    def update(self, dt):
        self.t += dt
        if self.flash > 0:
            self.flash -= dt
        if self.intro > 0:
            self.intro -= dt
            k = ease_out(1.0 - max(0.0, self.intro) / S.BOSS_INTRO_TIME)
            self.x = self.cx
            self.y = -self.h / 2 + (self.base_y + self.h / 2) * k
            if self.intro <= 0:
                self.invulnerable = False
                self.on_ready()
        else:
            self.think(dt)
            self._run_queue(dt)
        self.hb = self._calc_hb()

    def on_ready(self):
        pass

    def think(self, dt):
        pass

    def hit(self, dmg=S.SHOT_DAMAGE):
        if not self.alive or self.invulnerable:
            return False
        self.hp -= dmg
        self.flash = 0.06
        if self.hp <= 1e-9:
            return self.on_hp_zero()
        return False

    def on_hp_zero(self):
        self.hp = 0.0
        self.alive = False
        return True

    def hud_info(self):
        return dict(name=self.cfg["label"].upper(), ratio=clamp(self.hp / self.max_hp, 0.0, 1.0),
                    color=self.BAR_COLOR, tag="")

    def _move_sine(self, amp, speed, mult=1.0, bob=10.0):
        half = self.w / 2 + 10
        self.x = clamp(self.cx + amp * math.sin(self.mt * speed * mult), half, S.WIDTH - half)
        self.y = self.base_y + bob * math.sin(self.t * 2.2)

    def _draw_extra(self, surf):
        font = get_font(S.FONT_UI_NAME, 16, bold=True)
        info = self.hud_info()
        x0 = self.x - self.w / 2
        y0 = self.y - self.h / 2 - 22
        col = S.hx(info["color"])
        pygame.draw.rect(surf, S.hx("#12142a"), (x0, y0, self.w, 8), border_radius=3)
        pygame.draw.rect(surf, col, (x0 + 1, y0 + 1, (self.w - 2) * info["ratio"], 6), border_radius=2)
        pygame.draw.rect(surf, col, (x0, y0, self.w, 8), width=2, border_radius=3)
        label = font.render(info["name"] + (f" — {info['tag']}" if info["tag"] else ""), True, col)
        surf.blit(label, label.get_rect(midbottom=(int(self.x), int(y0 - 4))))


class Miniboss(Boss):
    """Round 5. Ataque A: foguetes giratórios (espiral). Ataque B: chuva de 3 balas."""
    BAR_COLOR = "#ff7a1a"

    def __init__(self, wave, x, hp):
        super().__init__(wave, "miniboss", x, S.MINIBOSS["base_y"], hp)
        self.rocket_t = S.MINIBOSS["first_attack"] + 1.2
        self.rain_t = S.MINIBOSS["first_attack"]

    def think(self, dt):
        c = S.MINIBOSS
        self.mt += self.mdt(dt)
        self._move_sine(c["amplitude"], c["speed"])
        ad = self.adt(dt)
        self.rocket_t -= ad
        self.rain_t -= ad
        if self.rocket_t <= 0:
            self.rocket_t = c["rocket_interval"]
            self.fire_rockets()
        if self.rain_t <= 0:
            self.rain_t = c["rain_interval"]
            self.fire_rain()

    def fire_rockets(self):
        g, c = self.game, S.MINIBOSS
        tgt = g.random_target()
        for i in range(c["rocket_count"]):
            side = -1 if i % 2 == 0 else 1
            px, py = self.x + side * 72, self.y + 56
            vx = clamp((tgt.x - px) * 0.16, -90.0, 90.0) if tgt else 0.0
            spiral = dict(gx=px, gy=py, gvx=vx, gvy=c["rocket_speed"], r0=c["rocket_radius"][0],
                          r1=c["rocket_radius"][1], omega=c["rocket_omega"] * side,
                          phase=random.uniform(0, math.tau), grow=c["rocket_grow"])
            g.spawn_hostile("rocket", px, py, spiral=spiral)

    def fire_rain(self):
        g, c = self.game, S.MINIBOSS
        tgt = g.random_target()
        base = math.atan2(tgt.x - self.x, tgt.y - 30 - self.y) if tgt else 0.0
        for i, off in enumerate((-c["rain_spread"], 0.0, c["rain_spread"])):
            self.schedule(i * c["rain_stagger"],
                          lambda a=base + off: g.polar_bullet(self.x, self.y + 50, a, c["rain_speed"]))

    def on_destroyed(self, game):
        game.fx.explosion(self.x, self.y, self.cfg["size"], "#ffffff", "#ff7a1a", self.cfg["fx"][2], priority=True)
        game.flash("#ffffff", 0.25)
        game.shake(0.6, 10)


class Mothership(Boss):
    """Round 6. Atira em todos os jogadores; ao morrer divide-se em mini-naves."""
    BAR_COLOR = "#b07cff"

    def __init__(self, wave, x, hp):
        super().__init__(wave, "mothership", x, S.MOTHERSHIP["base_y"], hp)
        self.shot_t = S.MOTHERSHIP["first_attack"]
        self.burst_t = S.MOTHERSHIP["first_attack"] + 2.4
        self.split_done = False

    def think(self, dt):
        c = S.MOTHERSHIP
        self.mt += self.mdt(dt)
        self._move_sine(c["amplitude"], c["speed"], bob=0.0)
        self.y = self.base_y + 26 * math.sin(self.mt * c["speed"] * 1.7) ** 2 + 8 * math.sin(self.t * 3.0)
        ad = self.adt(dt)
        self.shot_t -= ad
        self.burst_t -= ad
        if self.shot_t <= 0:
            self.shot_t = c["shot_interval"]
            for p in self.game.alive_players():
                self.game.aim_bullet(self.x, self.y + 34, p, c["shot_speed"])
        if self.burst_t <= 0:
            self.burst_t = c["burst_interval"]
            n = c["burst_count"]
            for i in range(n):
                a = -1.15 + 2.3 * i / (n - 1)
                self.game.polar_bullet(self.x, self.y + 36, a, c["burst_speed"])

    def on_destroyed(self, game):
        game.fx.explosion(self.x, self.y, self.cfg["size"], "#ffffff", "#b07cff", self.cfg["fx"][2], priority=True)
        game.flash("#ffffff", 0.2)
        game.shake(0.5, 9)
        if not self.split_done:
            self.split_done = True
            game.wave.spawn_minis(random.randint(*S.MOTHERSHIP["split"]), self.x, self.y)


class FinalBoss(Boss):
    """Round 10. Fase 1 (combate) -> regeneração (invulnerável) -> modo frenético."""
    BAR_COLOR = "#ff2a4d"
    PHASE_NAMES = ("FASE 1", "REGENERANDO", "FRENÉTICO")

    def __init__(self, wave, x, hp):
        super().__init__(wave, "finalboss", x, S.FINALBOSS["base_y"], hp)
        self.phase_i = 0
        self.atk_t = S.FINALBOSS["first_attack"]
        self.last_atk = None
        self.regen_t = 0.0
        self.regen_to = 0.0
        self.ring_t = 0.0

    @property
    def frenzy(self):
        return self.phase_i == 2

    def on_hp_zero(self):
        g, c = self.game, S.FINALBOSS
        if self.phase_i == 0:
            self.phase_i = 1
            self.invulnerable = True
            self.hp = 0.0
            self.regen_to = self.max_hp * c["regen_fraction"]
            self.regen_t = c["regen_time"]
            self.queue.clear()
            g.show_banner("REGENERAÇÃO DETECTADA", "o chefe está recuperando energia!", "#46f08a", 2.4, alert=True)
            g.flash("#46f08a", 0.30)
            g.shake(0.5, 9)
            return False
        self.hp = 0.0
        self.alive = False
        return True

    def _enter_frenzy(self):
        g = self.game
        self.phase_i = 2
        self.invulnerable = False
        self.hp = self.regen_to
        self.atk_t = 1.0
        g.show_banner("MODO FRENÉTICO", "o chefe está furioso!", "#ff2a4d", 2.2, alert=True)
        g.flash("#ff2a4d", 0.30)
        g.shake(0.6, 11)

    def interval(self):
        c = S.FINALBOSS
        base = c["interval"]
        if self.frenzy:
            base = max(c["min_interval"], base * c["frenzy_interval_mult"])
        return base * random.uniform(0.85, 1.15)

    def think(self, dt):
        c = S.FINALBOSS
        if self.phase_i == 1:
            self.regen_t -= dt
            k = 1.0 - max(0.0, self.regen_t) / c["regen_time"]
            self.hp = self.regen_to * k
            self.mt += self.mdt(dt) * 0.15
            self._move_sine(c["amplitude"] * 0.3, c["speed"])
            self.ring_t -= dt
            if self.ring_t <= 0:
                self.ring_t = 0.45
                self.game.fx.ring(self.x, self.y, 30, 150, "#46f08a", 0.7, 4)
            if self.regen_t <= 0:
                self._enter_frenzy()
            return
        self.mt += self.mdt(dt) * (c["frenzy_speed_mult"] if self.frenzy else 1.0)
        half = self.w / 2 + 10
        self.x = clamp(self.cx + c["amplitude"] * (math.sin(self.mt * c["speed"])
                        + 0.25 * math.sin(self.mt * c["speed"] * 2.3)), half, S.WIDTH - half)
        self.y = self.base_y + (16 if self.frenzy else 10) * math.sin(self.t * (3.0 if self.frenzy else 2.0))
        self.atk_t -= self.adt(dt)
        if self.atk_t <= 0:
            self.atk_t = self.interval()
            self._attack()

    def _attack(self):
        opts = ["aimed", "fan", "bombline"] if not self.frenzy else ["aimed", "fan", "radial", "orb", "bombline", "orb"]
        pool = [o for o in opts if o != self.last_atk] or opts
        self.last_atk = random.choice(pool)
        getattr(self, "_atk_" + self.last_atk)()

    def _atk_aimed(self):
        g, n = self.game, 5 if self.frenzy else 3
        gap = 0.13 if self.frenzy else 0.2
        for p in g.alive_players():
            for i in range(n):
                self.schedule(i * gap, lambda p=p: p.active and g.aim_bullet(self.x, self.y + 52, p,
                                                                              S.FINALBOSS["bullet_speed"]))

    def _atk_fan(self):
        g, n = self.game, 7 if self.frenzy else 5
        for i in range(n):
            g.polar_bullet(self.x, self.y + 52, -0.85 + 1.7 * i / (n - 1), S.FINALBOSS["bullet_speed"] * 0.9)

    def _atk_radial(self):
        g, n = self.game, 12
        for i in range(n):
            g.polar_bullet(self.x, self.y + 40, -1.45 + 2.9 * i / (n - 1), S.FINALBOSS["bullet_speed"] * 0.8)

    def _atk_bombline(self):
        g = self.game
        for i, off in enumerate((-96, -48, 0, 48, 96)):
            self.schedule(i * 0.1, lambda off=off: g.spawn_hostile("bomb", self.x + off, self.y + 60,
                                                                     vy=S.BOMB_SPEED + 40))

    def _atk_orb(self):
        g, c = self.game, S.FINALBOSS
        targets = g.alive_players()
        random.shuffle(targets)
        for p in targets[:2 if self.frenzy else 1]:
            dx, dy = p.x - self.x, (S.GROUND_Y - 40) - (self.y + 60)
            d = math.hypot(dx, dy) or 1.0
            g.spawn_hostile("orb", self.x, self.y + 60, vx=dx / d * c["orb_speed"], vy=dy / d * c["orb_speed"],
                             fuse=c["orb_fuse"], blast=c["orb_radius"], air_blast=c["orb_radius"])

    def hud_info(self):
        col = ("#ff2a4d", "#46f08a", "#ff7a1a")[self.phase_i]
        return dict(name="CHEFE FINAL", ratio=clamp(self.hp / self.max_hp, 0.0, 1.0), color=col,
                    tag=self.PHASE_NAMES[self.phase_i])

    def on_destroyed(self, game):
        game.fx.explosion(self.x, self.y, self.cfg["size"], "#ffffff", "#ff2a4d", self.cfg["fx"][2], priority=True)
        game.flash("#ffffff", 0.40)
        game.shake(1.0, 14)


# ---------------------------------------------------------------- carro cibernético e jatos
class CyberCar(Enemy):
    """Rounds 7/8. Só é destruído por 2 aterrissagens de pulo no teto."""
    solo = True
    breachable = False
    shootable = False

    def __init__(self, wave, x, speed, turbo=False):
        cfg = S.ENEMY_TYPES["car"]
        super().__init__(None, "car", x, S.GROUND_Y - cfg["h"] / 2, S.CAR["impacts"], 0.0)
        self.wave, self.game = wave, wave.game
        self.entry = 0.0
        self.y = S.GROUND_Y - self.h / 2
        self.speed = speed
        self.dir = random.choice((-1, 1))
        self.impacts_max = S.CAR["impacts"]
        self.impacts_left = S.CAR["impacts"]
        self.stomp_lock = 0.0
        self.turbo = turbo
        self.turbo_on = False
        self.turbo_t = random.uniform(*S.CAR["turbo_every"])
        self.spark_t = 0.0
        self.smoke_t = 0.0
        self.hb = self._calc_hb()

    @property
    def top(self):
        return self.hb[1]

    def update(self, dt):
        g = self.game
        self.t += dt
        if self.flash > 0:
            self.flash -= dt
        if self.stomp_lock > 0:
            self.stomp_lock -= dt
        sp = self.speed * g.enemy_move_mult
        if self.turbo:
            self.turbo_t -= dt
            if self.turbo_t <= 0:
                self.turbo_on = not self.turbo_on
                self.turbo_t = S.CAR["turbo_time"] if self.turbo_on else random.uniform(*S.CAR["turbo_every"])
            if self.turbo_on:
                sp *= S.CAR["turbo_mult"]
        old = self.x
        self.x += self.dir * sp * dt
        lo, hi = 14 + self.w / 2, S.WIDTH - 14 - self.w / 2
        if self.x <= lo:
            self.x, self.dir = lo, 1
        elif self.x >= hi:
            self.x, self.dir = hi, -1
        dx = self.x - old
        if dx:
            for p in g.players:
                if p.standing is self:
                    p.x += dx
        self.spark_t -= dt
        if self.spark_t <= 0:
            self.spark_t = S.CAR["spark_interval"] * (0.5 if self.turbo_on else 1.0)
            g.fx.sparks(self.x - self.dir * 58, S.GROUND_Y - 3, "#ffd23f", 2 if self.turbo_on else 1, up=True)
        if self.impacts_left < self.impacts_max:
            self.smoke_t -= dt
            if self.smoke_t <= 0:
                self.smoke_t = 0.12
                g.fx.sparks(self.x + random.uniform(-30, 30), self.y - 22, "#5a5f7a", 1, up=True)
        self.hb = self._calc_hb()

    def stomp(self, p):
        """Impacto válido de pulo. Retorna True se o carro foi destruído."""
        if not self.alive or self.stomp_lock > 0:
            return False
        g = self.game
        self.stomp_lock = S.CAR["stomp_lock"]
        self.impacts_left -= 1
        self.hp = float(self.impacts_left)
        self.flash = 0.14
        g.fx.sparks(p.x, self.top, "#ffe14d", 8, up=True)
        g.fx.popup(self.x, self.top - 40, "IMPACTO!", "#ffe14d", 20)
        g.shake(0.2, 5)
        if self.impacts_left <= 0:
            self.alive = False
            return True
        self.speed *= 1.25
        return False

    def _draw_extra(self, surf):
        x, y = int(self.x), int(self.y)
        for i in range(self.impacts_max):
            lit = i < self.impacts_left
            col = S.hx("#ffe14d") if lit else S.hx("#3a3f5e")
            rect = (x - 18 + i * 24, y - 36, 12, 6)
            if lit:
                draw_glow_circle(surf, rect[0] + 6, rect[1] + 3, 10, col, intensity=0.7, layers=2)
            pygame.draw.rect(surf, col, rect, border_radius=2)
        font = get_font(S.FONT_UI_NAME, 13, bold=True)
        hint = font.render("▼ PULE EM CIMA", True, S.hx("#ffe14d"))
        surf.blit(hint, hint.get_rect(center=(x, y - 50)))


class Jet(Enemy):
    """Round 9. Cruza a arena lançando bombas destrutíveis; sai de cena e volta."""
    solo = True
    breachable = False

    def __init__(self, wave, hp, delay, lane):
        super().__init__(None, "jet", -999.0, lane, hp, 0.0)
        self.wave, self.game = wave, wave.game
        self.entry = 0.0
        self.lane = lane
        self.state = "wait"
        self.wait_t = delay
        self.dir = 1
        self.bomb_t = 0.0
        self.hb = HIDDEN_HB

    def update(self, dt):
        g = self.game
        self.t += dt
        if self.flash > 0:
            self.flash -= dt
        if self.state == "wait":
            self.wait_t -= dt
            if self.wait_t <= 0:
                self._launch()
            self.hb = HIDDEN_HB if self.state == "wait" else self._calc_hb()
            return
        sp = S.ENEMY_TYPES["jet"]["speed"] * self.wave.diff_speed * g.enemy_move_mult
        self.x += self.dir * sp * dt
        if 60 < self.x < S.WIDTH - 60:
            self.bomb_t -= dt * g.enemy_attack_rate
            if self.bomb_t <= 0:
                self.bomb_t = S.JET["bomb_interval"]
                self._drop()
        if (self.dir > 0 and self.x > S.WIDTH + self.w) or (self.dir < 0 and self.x < -self.w):
            self.state = "wait"
            self.wait_t = random.uniform(*S.JET["away_time"])
            self.x = -999.0
        self.hb = HIDDEN_HB if self.state == "wait" else self._calc_hb()

    def _launch(self):
        self.lane = random.choice(S.JET["lanes"])
        self.dir = random.choice((-1, 1))
        self.y = self.lane
        self.x = -self.w if self.dir > 0 else S.WIDTH + self.w
        self.flip = self.dir
        self.state = "cross"
        self.bomb_t = 0.35

    def _drop(self):
        g = self.game
        hp = max(1, int(round(S.JET_BOMB["hp"] * g.diff["enemy_hp"])))
        vx = self.dir * S.ENEMY_TYPES["jet"]["speed"] * S.JET["bomb_vx_factor"]
        g.spawn_hostile("jetbomb", self.x, self.y + 18, vx=vx, vy=S.JET_BOMB["speed"], hp=float(hp),
                         blast=S.JET_BOMB["ground_radius"], air_blast=S.JET_BOMB["air_radius"])

    def _draw_extra(self, surf):
        x, y = int(self.x), int(self.y)
        flame_col = S.hx("#ff8a1f") if int(self.t * 20) % 2 == 0 else S.hx("#ffe14d")
        tail = -self.flip * 20
        pygame.draw.polygon(surf, flame_col, [(x + tail - 4, y - 4), (x + tail - 4, y + 4), (x + tail - 14, y)])
