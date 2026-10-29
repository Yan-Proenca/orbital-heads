"""
collisions.py — colisões geométricas (AABB; círculo x retângulo nas
explosões em área). Porte fiel de CollisionManager em main.py, usando a
mesma grade espacial (SpatialGrid) para tiro x alvo quando há muitos pares.
"""
import settings as S
from projectile import Projectile
from squad import SpatialGrid
from utils import overlap


class CollisionManager:
    def __init__(self, game):
        self.game = game
        self.grid = SpatialGrid()
        self.pairs_checked = 0

    def update(self):
        self.shots_vs_enemies()
        self.bombs_vs_players()
        self.enemies_vs_players()
        self.pickups_vs_players()
        self.breach()

    # ------------------------------------------------------------ tiros dos jogadores
    def shots_vs_enemies(self):
        g = self.game
        shots = [b for b in g.projectiles if b.alive and b.owner is not None]
        if not shots:
            return
        targets = [e for e in g.wave.enemies if e.alive and e.shootable]
        targets += [b for b in g.projectiles if b.alive and b.owner is None and b.hp is not None and not b.exploded]
        if not targets:
            return
        use_grid = S.USE_SPATIAL_GRID and len(targets) * len(shots) > S.GRID_MIN_PAIRS
        if use_grid:
            self.grid.rebuild(targets)
        checked = 0
        for b in shots:
            hb = b.hb
            cand = self.grid.query(hb) if use_grid else targets
            best = None
            for t in cand:
                if not t.alive:
                    continue
                th = t.hb
                checked += 1
                if th[0] < hb[2] and th[2] > hb[0] and th[1] < hb[3] and th[3] > hb[1]:
                    if best is None or th[3] > best.hb[3]:
                        best = t
            if best is None:
                continue
            b.alive = False
            color = b.color or (S.hx(b.owner.cfg["bullet"]) if b.owner else (255, 255, 255))
            g.fx.impact(b.x, best.hb[3], color)
            if isinstance(best, Projectile):
                if best.hit(b.damage):
                    g.on_projectile_destroyed(best, b.owner)
            elif best.hit(b.damage):
                g.on_enemy_destroyed(best, b.owner)
        self.pairs_checked = checked

    # ------------------------------------------------------------ projéteis inimigos x jogadores
    def bombs_vs_players(self):
        g = self.game
        for b in g.projectiles:
            if not b.alive or b.owner is not None:
                continue
            hb = b.hb
            for p in g.players:
                if p.can_be_hit() and overlap(hb, p.hitbox()):
                    if b.blast:
                        g.detonate(b, "air")
                    else:
                        b.alive = False
                        g.fx.impact(b.x, b.y, S.hx("#ff7a1a"))
                        p.take_hit()
                    break

    # ------------------------------------------------------------ contato
    def enemies_vs_players(self):
        g = self.game
        enemies = g.wave.enemies
        if not enemies:
            return
        for p in g.players:
            if not p.can_be_hit():
                continue
            hb = p.hitbox()
            for e in enemies:
                if not e.alive or not e.contact_damage or p.standing is e:
                    continue
                eh = e.hb
                if eh[0] < hb[2] and eh[2] > hb[0] and eh[1] < hb[3] and eh[3] > hb[1]:
                    p.take_hit()
                    break

    # ------------------------------------------------------------ itens
    def pickups_vs_players(self):
        g = self.game
        for pk in g.pickups:
            if not pk.alive or pk.collected:
                continue
            for p in g.players:
                if p.active and overlap(p.hitbox(), pk.hb):
                    g.collect(p, pk)
                    break

    # ------------------------------------------------------------ invasão
    def breach(self):
        """Inimigo que alcança a linha de perigo invade a base: explode e cada jogador vivo perde 1 vida."""
        g, w = self.game, self.game.wave
        if w.state != "active":
            return
        if not any(e.breachable and e.y + e.h / 2 >= S.DANGER_Y for e in w.enemies):
            return
        for e in [e for e in w.enemies if e.breachable and e.y + e.h / 2 >= S.DANGER_Y - S.BREACH_CLEAR_MARGIN]:
            cfg = e.cfg
            g.fx.explosion(e.x, e.y, cfg["size"], *cfg["fx"])
            w.remove_enemy(e)
        if g.breach_cd <= 0:
            g.breach_cd = S.BREACH_COOLDOWN
            g.flash("#ff2a4d", 0.30)
            g.shake(0.40, 10)
            g.show_banner("INVASÃO!", "-1 vida para cada jogador", "#ff4d6d", 1.4)
            g.audio.play_sfx("breach")
            for p in g.players:
                if not p.eliminated:
                    p.take_hit(force=True)
