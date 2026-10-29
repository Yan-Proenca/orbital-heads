"""
player.py — física, armas e boosts individuais do jogador (porte fiel da
classe Player de main.py). O desenho usa um "robozinho" poligonal simples
feito com pygame.draw, equivalente em leitura ao sprite original.
"""
import math

import pygame

import settings as S
from utils import clamp, approach, mult_clamp, get_font


class Player:
    W = 34
    HIT_W = 26
    HIT_H = 60

    def __init__(self, game, idx, cfg):
        self.game = game
        self.idx = idx
        self.cfg = cfg
        self.prefix = f"p{idx + 1}_"
        self.name = cfg["name"]
        self.short = cfg["short"]
        self.color = S.hx(cfg["color"])
        self.lives = S.PLAYER_LIVES
        self.score = 0
        self.kills = 0
        self.kills_by_type = {k: 0 for k in S.ENEMY_TYPES}
        self.eliminated = False
        self.dead = False
        self.respawn_timer = 0.0
        self.dash_cd = 0.0
        self.weapon = "standard"
        self.effects = {}
        self.muzzle_len = 0.07
        self._init_motion()

    def _init_motion(self):
        self.x = self.cfg["spawn_x_frac"] * S.WIDTH
        self.y = float(S.GROUND_Y)
        self.vx = self.vy = 0.0
        self.on_ground = True
        self.facing = self.cfg["facing"]
        self.last_dir = 0
        self.dash_dir = self.facing
        self.dash_timer = 0.0
        self.trail_t = 0.0
        self.shoot_cd = 0.0
        self.muzzle_t = 0.0
        self.invuln = 0.0
        self.squash = 0.0
        self.anim_phase = 0.0
        self.prev_y = float(S.GROUND_Y)
        self.standing = None

    # ---------------------------------------------------------- estado
    @property
    def active(self):
        return not self.dead and not self.eliminated

    def can_be_hit(self):
        if not self.active or self.invuln > 0 or "shield" in self.effects:
            return False
        return not (S.DASH_INVULNERABLE and self.dash_timer > 0)

    # ---------------------------------------------------------- armas e boosts
    def speed_mult(self):
        return mult_clamp([S.BOOSTS[k]["speed"] for k in self.effects if "speed" in S.BOOSTS[k]],
                           S.PLAYER_SPEED_MULT_LIMITS)

    def interval_mult(self):
        return mult_clamp([S.BOOSTS[k]["fire_interval"] for k in self.effects if "fire_interval" in S.BOOSTS[k]],
                           S.FIRE_INTERVAL_MULT_LIMITS)

    def add_effect(self, key):
        self.effects[key] = S.BOOSTS[key]["duration"]

    def set_weapon(self, key):
        self.weapon = key
        self.shoot_cd = 0.0

    def clear_boosts(self):
        self.effects.clear()
        if S.WEAPON_RESET_ON_DEATH:
            self.weapon = "standard"

    def hitbox(self):
        return (self.x - self.HIT_W / 2, self.y - self.HIT_H, self.x + self.HIT_W / 2, self.y)

    def count_shots(self):
        return sum(1 for b in self.game.projectiles if b.alive and b.owner is self)

    # ---------------------------------------------------------- lógica
    def update(self, dt):
        if self.eliminated:
            return
        if self.dead:
            self.respawn_timer -= dt
            if self.respawn_timer <= 0:
                self.respawn()
            return

        g = self.game
        held = g.input.held
        just = g.just

        def act(name):
            return self.prefix + name

        self.shoot_cd = max(-dt, self.shoot_cd - dt)
        self.invuln = max(0.0, self.invuln - dt)
        self.dash_cd = max(0.0, self.dash_cd - dt)
        self.muzzle_t = max(0.0, self.muzzle_t - dt)
        self.squash = max(0.0, self.squash - dt * 6.0)

        if self.effects:
            for key in list(self.effects):
                self.effects[key] -= dt
                if self.effects[key] <= 0:
                    del self.effects[key]

        vmax = S.PLAYER_SPEED * self.speed_mult()

        move = (act("right") in held) - (act("left") in held)
        if move:
            self.facing = move
            self.last_dir = move

        # --- dash
        if self.dash_timer <= 0 and act("dash") in just and self.dash_cd <= 0:
            self.dash_dir = move or self.last_dir or self.facing
            self.dash_timer = S.DASH_DURATION
            self.dash_cd = S.DASH_COOLDOWN + S.DASH_DURATION
            self.trail_t = 0.0
            self.last_dir = self.dash_dir
            g.audio.on_dash()

        if self.dash_timer > 0:
            self.dash_timer -= dt
            self.vx = self.dash_dir * S.DASH_SPEED
            self.vy = 0.0
            self.trail_t -= dt
            if self.trail_t <= 0:
                self.trail_t = 0.025
                g.fx.dash_trail(self)
            if self.dash_timer <= 0:
                self.dash_timer = 0.0
                self.vx = self.dash_dir * vmax
        else:
            accel = S.PLAYER_ACCEL if self.on_ground else S.PLAYER_AIR_ACCEL
            if move:
                self.vx = approach(self.vx, move * vmax, accel * dt)
            else:
                self.vx = approach(self.vx, 0.0, S.PLAYER_FRICTION * dt)

            if self.on_ground and act("jump") in just:
                self.vy = -S.JUMP_SPEED
                self.on_ground = False
                g.fx.dust(self.x, S.GROUND_Y, 4)
                g.audio.on_jump()

            self.vy = min(self.vy + S.GRAVITY * dt, S.MAX_FALL)

        # --- integração + limites da arena
        self.prev_y = self.y
        self.x += self.vx * dt
        self.y += self.vy * dt
        half = self.W / 2 + S.ARENA_MARGIN
        if self.x < half or self.x > S.WIDTH - half:
            self.x = clamp(self.x, half, S.WIDTH - half)
            if self.dash_timer <= 0:
                self.vx = 0.0

        # --- chão ou plataforma móvel (topo do carro): só pousa descendo
        floor, support = float(S.GROUND_Y), None
        for car in g.wave.cars:
            if (car.alive and self.vy >= 0 and self.prev_y <= car.hb[1] + 6 and self.y >= car.hb[1]
                    and self.x + self.HIT_W / 2 > car.hb[0] and self.x - self.HIT_W / 2 < car.hb[2]
                    and car.hb[1] < floor):
                floor, support = car.hb[1], car
        if self.y >= floor:
            if not self.on_ground and self.vy > 120:
                self.squash = 1.0
                g.fx.dust(self.x, floor, 6)
            self.y = float(floor)
            if self.vy > 0:
                self.vy = 0.0
            was_air = not self.on_ground
            self.on_ground = True
            if support is not None and (was_air or self.standing is not support):
                g.on_stomp(support, self)
            self.standing = support
        else:
            self.on_ground = False
            self.standing = None
        if self.on_ground:
            self.anim_phase += abs(self.vx) * dt * 0.055

        # --- tiro
        weapon = S.WEAPONS[self.weapon]
        if act("fire") in held and self.shoot_cd <= 0 and self.count_shots() < weapon["max_proj"]:
            g.fire_weapon(self, weapon)
            self.shoot_cd += weapon["interval"] * self.interval_mult()
            self.muzzle_len = self.muzzle_t = weapon["muzzle"]

        self.anim_phase += dt * (8.0 if (move or self.dash_timer > 0) else 0.0)

    def take_hit(self, force=False):
        """Perde uma vida. force=True ignora invulnerabilidade (penalidade de invasão)."""
        if self.eliminated or (not force and not self.can_be_hit()):
            return False
        g = self.game
        self.lives -= 1
        was_dead = self.dead
        if not was_dead:
            c = self.cfg
            g.fx.explosion(self.x, self.y - 30, 50, "#ffffff", c["color"], (c["color"], c["light"], "#ffd23f"))
            g.flash("#ff2a4d", 0.20)
            g.shake(0.30, 8)
            g.audio.on_player_hit()
        self.dash_timer = 0.0
        self.vx = self.vy = 0.0
        self.standing = None
        self.clear_boosts()
        if self.lives <= 0:
            self.lives = 0
            self.dead = False
            self.eliminated = True
            g.audio.on_player_death()
            g.on_player_eliminated(self)
        else:
            self.dead = True
            self.respawn_timer = S.RESPAWN_DELAY
        return True

    def respawn(self):
        self._init_motion()
        self.dead = False
        self.invuln = S.INVULN_TIME
        self.game.fx.dust(self.x, S.GROUND_Y, 6)

    # ---------------------------------------------------------- desenho
    # ---------------------------------------------------------- desenho
    def draw(self, surf):
        if self.eliminated:
            x = clamp(self.x, 110, S.WIDTH - 110)
            font = get_font(S.FONT_UI_NAME, 22, bold=True)
            img = font.render("GAME OVER", True, S.hx("#ff4d6d"))
            surf.blit(img, img.get_rect(center=(int(x), S.GROUND_Y - 34)))
            return
        if self.dead:
            return
        if self.invuln > 0 and int(self.invuln * 14) % 2 == 1:   # pisca ao renascer
            return

        cfg = self.cfg
        x, y = self.x, self.y
        sx = sy = 1.0
        if self.squash > 0:
            sx += 0.20 * self.squash
            sy -= 0.18 * self.squash
        elif not self.on_ground and self.vy < -150:
            sx -= 0.06
            sy += 0.07
        lean = self.dash_dir * 0.30 if self.dash_timer > 0 else clamp(self.vx / S.PLAYER_SPEED, -1, 1) * 0.07

        def P(rx, ry):
            return (x + (rx - lean * ry) * sx, y + ry * sy)

        ph = self.anim_phase
        running = self.on_ground and abs(self.vx) > 25 and self.dash_timer <= 0
        
        # Animação fluida de membros ao correr
        if not self.on_ground:
            l_off, r_off = (-6.0, 4.0), (6.0, 4.0)
        elif running:
            s_, c_ = math.sin(ph * 1.5), math.cos(ph * 1.5)
            l_off, r_off = (s_ * 8, max(0.0, c_) * 5), (-s_ * 8, max(0.0, -c_) * 5)
        else:
            l_off = r_off = (0.0, 0.0)

        bob = abs(math.sin(ph)) * 2.5 if running else 0.0
        recoil = 4.0 * (self.muzzle_t / self.muzzle_len) if self.muzzle_t > 0 else 0.0
        ub = -bob + recoil

        color = S.hx(cfg["color"])
        dark = S.hx(cfg["dark"])
        light = S.hx(cfg["light"])
        visor = S.hx(cfg["visor"])

        # --- 1. Mochila Propulsora (Jetpack traseiro)
        jp_poly = [P(-15, -45 + ub), P(-8, -45 + ub), P(-10, -20 + ub), P(-16, -22 + ub)]
        pygame.draw.polygon(surf, dark, jp_poly)
        pygame.draw.polygon(surf, light, [P(-13, -38 + ub), P(-10, -38 + ub), P(-10, -28 + ub), P(-13, -28 + ub)])

        # --- 2. Pernas / Rodas com estilo mecânico
        pygame.draw.polygon(surf, dark, [P(-12 + l_off[0], -20 - l_off[1]), P(-4 + l_off[0], -20 - l_off[1]), P(-2 + l_off[0], 0), P(-10 + l_off[0], 0)])
        pygame.draw.polygon(surf, dark, [P(4 + r_off[0], -20 - r_off[1]), P(12 + r_off[0], -20 - r_off[1]), P(10 + r_off[0], 0), P(2 + r_off[0], 0)])
        # Pés / Botas energizadas
        pygame.draw.polygon(surf, light, [P(-14 + l_off[0], -4), P(-2 + l_off[0], -4), P(-2 + l_off[0], 0), P(-14 + l_off[0], 0)])
        pygame.draw.polygon(surf, light, [P(2 + r_off[0], -4), P(14 + r_off[0], -4), P(14 + r_off[0], 0), P(2 + r_off[0], 0)])

        # --- 3. Torso e Armadura com Ombreiras Estilizadas
        torso_poly = [P(-13, -48 + ub), P(13, -48 + ub), P(15, -18 + ub), P(-15, -18 + ub)]
        pygame.draw.polygon(surf, color, torso_poly)
        
        # Núcleo de energia no peito (Reator Arc / LED central)
        pygame.draw.polygon(surf, light, [P(-6, -38 + ub), P(6, -38 + ub), P(4, -28 + ub), P(-4, -28 + ub)])
        pygame.draw.polygon(surf, visor, [P(-3, -35 + ub), P(3, -35 + ub), P(2, -31 + ub), P(-2, -31 + ub)])

        # Ombreiras blindadas laterais
        pygame.draw.polygon(surf, light, [P(-18, -48 + ub), P(-12, -48 + ub), P(-10, -32 + ub), P(-17, -34 + ub)])
        pygame.draw.polygon(surf, light, [P(12, -48 + ub), P(18, -48 + ub), P(17, -34 + ub), P(10, -32 + ub)])

        # --- 4. Cabeça / Capacete Futurista
        head_poly = [P(-11, -62 + ub), P(11, -62 + ub), P(13, -46 + ub), P(-13, -46 + ub)]
        pygame.draw.polygon(surf, dark, head_poly)

        # Viseira de LED horizontal imponente (marca registrada do personagem)
        visor_poly = [P(-9, -58 + ub), P(9, -58 + ub), P(8, -52 + ub), P(-8, -52 + ub)]
        pygame.draw.polygon(surf, visor, visor_poly)
        # Brilho central da viseira
        pygame.draw.polygon(surf, S.hx("#ffffff"), [P(-4, -56 + ub), P(4, -56 + ub), P(3, -54 + ub), P(-3, -54 + ub)])

        # --- 5. Canhão / Arma Principal acoplada ao ombro/braço
        barrel_col = S.WEAPONS[self.weapon]["color"] or "#b9c4e6"
        gun_mount = [P(3, -52 + ub), P(16, -52 + ub), P(15, -68 + ub), P(2, -64 + ub)]
        pygame.draw.polygon(surf, S.hx(dark), gun_mount)
        
        barrel_poly = [P(6, -72 + ub), P(11, -72 + ub), P(10, -60 + ub), P(5, -60 + ub)]
        pygame.draw.polygon(surf, S.hx(barrel_col), barrel_poly)

        # --- 6. Chama do dash / propulsor / pulo
        if self.dash_timer > 0 or (not self.on_ground and self.vy < -200):
            fl = 16 + 8 * math.sin(self.anim_phase * 10 + pygame.time.get_ticks() / 20.0)
            if self.dash_timer > 0:
                d = self.dash_dir
                pts = [P(-d * 16, -38), P(-d * 16, -24), P(-d * (36 + fl), -31)]
            else:
                pts = [P(-12, -18), P(-6, -18), P(-9, -18 - fl)]
            pygame.draw.polygon(surf, S.hx("#00f0ff"), pts)

        # --- 7. Clarão do Disparo (Muzzle Flash)
        if self.muzzle_t > 0:
            pts = [P(5, -72 + ub), P(12, -72 + ub), P(8.5, -92 + ub)]
            pygame.draw.polygon(surf, (255, 255, 255), pts)

        # --- 8. Nome do Jogador Flutuante Estilizado
        font = get_font(S.FONT_UI_NAME, 13, bold=True)
        label = font.render(cfg["short"], True, S.hx(cfg["color"]))
        surf.blit(label, label.get_rect(center=(int(x), int(y - 102))))

        # --- 9. Escudo (Shield) Energizado
        left = self.effects.get("shield", 0.0)
        if left > 0 and not (left < 1.2 and int(left * 8) % 2 == 1):
            rect = pygame.Rect(0, 0, 64, 94)
            rect.center = (int(x), int(y - 40))
            pygame.draw.ellipse(surf, S.hx(S.BOOSTS["shield"]["color"]), rect, width=2)