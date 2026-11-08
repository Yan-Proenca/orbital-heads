#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
selftest_hazards.py — testes automáticos (sem janela/áudio) da atualização "vida extra + doação + hazards".

    python selftest_hazards.py            # roda tudo
    python selftest_hazards.py saws pods  # só os testes cujo nome contém estas palavras

Usa SDL "dummy": não abre janela nem precisa de placa de som. Cada teste cria uma partida nova (Game real),
avança o jogo quadro a quadro com Game.step() e confere o estado — passando pelos mesmos caminhos de
colisão/atualização do jogo de verdade.
"""
import math
import os
import random
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame

pygame.init()
pygame.display.set_mode((1280, 720))

import settings as S
import hazards as HZ
from game import Game
from enemy import CyberCar
from game_modes import CrazyCarMode
from projectile import Projectile

DT = 1 / 60
FAILS = []
SCREEN = pygame.display.get_surface()


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print("      FALHOU:", msg)
    return cond


# ----------------------------------------------------------------------------- helpers
def mk(players=2, difficulty="normal", mode=None, seed=7):
    random.seed(seed)
    g = Game(SCREEN)
    g.player_count = players
    g.difficulty = difficulty
    if mode:
        g.game_mode = mode
    g.start_match()
    return g


def tick(g, n=1, press=(), shield=True, draw=False):
    """Avança n quadros. shield=True mantém os jogadores invulneráveis (testes de fluxo)."""
    for _ in range(n):
        if shield:
            for p in g.players:
                if p.active:
                    p.effects["shield"] = 999.0
        g.input.update()
        g.input.pressed |= set(press)
        press = ()
        g.step(DT)
        if draw:
            g.draw(SCREEN)


def until(g, cond, limit=60 * 120, **kw):
    for i in range(limit):
        if cond():
            return i
        tick(g, 1, **kw)
    return None


def to_combat(g, n):
    """Pula direto para o round n e espera os inimigos nascerem (estado 'active')."""
    g.wave.begin_round(n)
    assert until(g, lambda: g.wave.state == "active", limit=60 * 20) is not None, "round não chegou a 'active'"


def kill_enemies(g, killer=None):
    killer = killer or g.players[0]
    for _ in range(6):                       # nave-mãe gera minis ao morrer: repete até esvaziar
        es = list(g.wave.enemies)
        if not es:
            break
        for e in es:
            if e.alive or True:
                g.on_enemy_destroyed(e, killer)


def shoot_up(g, owner, x, y, dmg=1.0):
    """Insere um tiro real do jogador em (x, y); as colisões do próximo quadro decidem o resto."""
    b = Projectile(owner, x, y, -900.0, damage=dmg)
    g.projectiles.append(b)
    return b


def eliminate(g, p):
    p.lives = 1
    p.invuln = 0.0
    p.effects.clear()
    assert p.take_hit(force=True)
    assert p.eliminated


def hazard_counts(g):
    hz = g.wave.hazards
    return dict(saws=len(hz.saws), rockets=len(hz.rockets), pods=len(hz.pods),
                balls=len(hz.balls), spheres=len(hz.spheres))


EXPECTED_ORDER = {n: [ph for ph in cfg["order"]] for n, cfg in S.HAZARD_ROUNDS.items()}


# ============================================================================= testes
def test_keybinds_unicas():
    g = mk(4)
    codes = {}
    for i, b in enumerate(g.input.bindings):
        check("donate_life" in b.key_codes, f"P{i+1} sem donate_life")
        for act, code in b.key_codes.items():
            who = f"P{i+1}.{act}"
            check(code not in codes, f"tecla repetida: {who} e {codes.get(code)}")
            codes[code] = who
    reserved = (pygame.K_ESCAPE, pygame.K_r, pygame.K_m, pygame.K_q, pygame.K_F11, pygame.K_f,
                pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4)
    for code in reserved:
        check(code not in codes, f"donate/ações colidem com tecla global {pygame.key.name(code)}")
    check("donate_life" in S.GAMEPAD_BUTTONS and S.GAMEPAD_BUTTONS["donate_life"] not in
          (S.GAMEPAD_BUTTONS[k] for k in ("jump", "dash", "fire", "pause")), "botão de gamepad de doação repetido")
    # remapeamento: a ação aparece na tela de configuração e aceita rebind
    import game as G
    check("donate_life" in G.REBIND_ACTIONS and "donate_life" in G.REBIND_ACTION_LABELS, "donate_life fora da tela de remapeamento")
    g.input.rebind_key(0, "donate_life", "h")
    check(g.input.bindings[0].key_codes["donate_life"] == pygame.K_h, "rebind de donate_life não aplicou")
    check(g.input.key_display(0, "donate_life") == "H", "label de donate_life após rebind")
    # gamepad simulado: botão Y vira p1_donate_life
    gp = g.input.gamepad
    gp.is_connected = lambda slot: True
    gp.button_down = lambda slot, name: name == "y"
    gp.axis_dir = lambda slot, deadzone=0.5: (0, 0)
    g.input.bindings[0].gamepad_slot = 0
    g.input.update()
    check("p1_donate_life" in g.input.held, "botão Y do controle não gerou p1_donate_life")


def test_chance_vida_por_round():
    g = mk(2)
    exp = {1: 0, 2: 0, 3: 0, 4: .03, 5: .03, 6: .05, 7: .05, 8: .07, 9: .07, 10: .09, 11: .09, 30: .09}
    for r, c in exp.items():
        check(abs(g.life_drop_chance(r) - c) < 1e-9, f"chance round {r}: {g.life_drop_chance(r)} != {c}")


def test_drop_de_vida_estatistico():
    g = mk(2)
    cfg = S.LIFE_BOOST
    saved = (cfg["max_per_round"], cfg["max_active"])
    cfg["max_per_round"], cfg["max_active"] = 10 ** 9, 10 ** 9      # desliga as travas para medir só a probabilidade
    try:
        for rnd, chance in ((3, 0.0), (4, .03), (7, .05), (9, .07), (10, .09)):
            g.wave.round_no = rnd
            N, hits = 30000, 0
            for _ in range(N):
                g.pickups.clear()
                if g.roll_life_drop("drone", 400, 200):
                    hits += 1
            rate = hits / N
            tol = 0.0 if chance == 0 else 4 * math.sqrt(chance * (1 - chance) / N)
            check(abs(rate - chance) <= tol + 1e-9, f"round {rnd}: taxa {rate:.4f} vs {chance} (tol {tol:.4f})")
        g.wave.round_no = 10
        for kind in ("finalboss", "jetbomb"):
            check(all(g.roll_life_drop(kind, 400, 200) is None for _ in range(2000)), f"{kind} não deveria dropar vida")
    finally:
        cfg["max_per_round"], cfg["max_active"] = saved
    # travas de balanceamento
    g.pickups.clear()
    g.wave.round_no = 10
    g.life_drops_this_round = 0
    orig = S.LIFE_BOOST["chance_by_round"]
    S.LIFE_BOOST["chance_by_round"] = ((1, 1.0),)
    try:
        for _ in range(20):
            g.roll_life_drop("drone", 300, 200)
        n = sum(1 for p in g.pickups if p.kind == "life")
        check(n == S.LIFE_BOOST["max_active"], f"max_active não respeitado: {n}")
        g.pickups.clear()
        g.life_drops_this_round = 0
        for _ in range(20):
            g.roll_life_drop("drone", 300, 200)
            g.pickups.clear()
            if g.life_drops_this_round >= S.LIFE_BOOST["max_per_round"]:
                break
        check(g.life_drops_this_round == S.LIFE_BOOST["max_per_round"], "max_per_round não respeitado")
    finally:
        S.LIFE_BOOST["chance_by_round"] = orig


def test_item_de_vida_ciclo_completo():
    g = mk(2)
    g.wave.round_no = 5
    p1, p2 = g.players
    # drop acontece na posição do inimigo abatido, via on_enemy_destroyed
    S.LIFE_BOOST["chance_by_round"], orig = ((1, 1.0),), S.LIFE_BOOST["chance_by_round"]
    try:
        to_combat(g, 4)
        e = next(e for e in g.wave.enemies if e.kind in S.LIFE_BOOST["eligible"])
        ex, ey = e.x, e.y
        g.on_enemy_destroyed(e, p1)
    finally:
        S.LIFE_BOOST["chance_by_round"] = orig
    lives = [pk for pk in g.pickups if pk.kind == "life"]
    check(len(lives) == 1, "o abate não gerou o item de vida")
    pk = lives[0]
    check(abs(pk.x - clampx(ex)) < 1 and abs(pk.y - max(S.HUD_H + 20, min(ey, S.GROUND_Y - 60))) < 1, "item não nasceu na posição do inimigo")
    check(pk.good and pk.life == S.LIFE_BOOST["lifetime"], "good/lifetime do item de vida")
    # cai até o chão
    y0 = pk.y
    tick(g, 10)
    check(pk.y > y0 or pk.landed, "item não caiu")
    until(g, lambda: pk.landed, limit=60 * 10)
    check(pk.landed and abs(pk.y - (S.GROUND_Y - pk.R)) < 1, "item não pousou no chão")
    # coleta: +1 vida, uma única vez
    p1.lives = 3
    p1.x = pk.x
    p1.y = S.GROUND_Y
    tick(g, 2)
    check(p1.lives == 4, f"coleta deveria dar +1 vida (tem {p1.lives})")
    check(pk.collected and not pk.alive, "item deveria estar consumido")
    tick(g, 5)
    check(p1.lives == 4, "item de vida coletado duas vezes")
    # expira se ninguém pegar (e não pisca antes de pousar)
    pk2 = g.spawn_life_pickup(900, 300)
    p1.x = p2.x = 100
    until(g, lambda: pk2.landed, limit=60 * 10)
    t_land = g.match_time
    until(g, lambda: not pk2.alive, limit=60 * 20)
    check(not pk2.alive and not pk2.collected, "item não expirou")
    check(abs((g.match_time - t_land) - S.LIFE_BOOST["lifetime"]) < 0.3, f"tempo de permanência != configurado ({g.match_time - t_land:.2f}s)")
    # teto de vidas: quem está no teto não coleta (sobra para o aliado)
    p1.lives = S.LIFE_BOOST["max_lives"]
    p2.lives = 2
    pk3 = g.spawn_life_pickup(600, S.GROUND_Y - 20)
    pk3.landed, pk3.y = True, S.GROUND_Y - pk3.R
    p1.x = p2.x = 600
    tick(g, 3)
    check(p1.lives == S.LIFE_BOOST["max_lives"] and p2.lives == 3, "vida deveria ir para quem não está no teto")


def clampx(x):
    return max(30, min(S.WIDTH - 30, x))


def test_doacao_basica_e_regras():
    g = mk(2)
    p1, p2 = g.players
    P = lambda *a: tick(g, 1, press=a, shield=False)
    # sem aliado caído: nada é consumido
    p1.lives = 3
    P("p1_donate_life")
    check(p1.lives == 3, "doou sem aliado caído")
    tick(g, 30, shield=False)
    # aliado só 'morto' (respawn automático) NÃO é alvo
    p2.lives = 2
    p2.invuln = 0
    p2.take_hit(force=True)
    check(p2.dead and not p2.eliminated, "estado dead esperado")
    P("p1_donate_life")
    check(p1.lives == 3 and p2.lives == 1, "doou para jogador que apenas renasce sozinho")
    tick(g, int(60 * (S.RESPAWN_DELAY + 0.3)), shield=False)
    check(p2.active, "p2 deveria ter renascido sozinho")
    # eliminado de verdade
    eliminate(g, p2)
    check(g.revive_hint(p2) is not None, "dica de ajuda deveria aparecer (doador com vidas)")
    # doador com 1 vida: bloqueado
    p1.lives = 1
    P("p1_donate_life")
    check(p1.lives == 1 and p2.eliminated, "doador com 1 vida não pode doar")
    check(g.revive_hint(p2) is None, "dica não deveria aparecer sem doador elegível")
    tick(g, 30, shield=False)
    # doador com exatamente 2 vidas
    p1.lives = 2
    P("p1_donate_life")
    check(p1.lives == 1 and p1.active, f"doador deveria ficar com 1 vida (tem {p1.lives})")
    check(not p2.eliminated and not p2.dead and p2.active, "aliado deveria estar de volta")
    check(p2.lives == S.LIFE_DONATION["revive_lives"] == 1, f"aliado deveria voltar com 1 vida (tem {p2.lives})")
    check(abs(p2.invuln - S.LIFE_DONATION["invuln"]) < 0.1, f"invulnerabilidade pós-revive: {p2.invuln}")
    check(S.ARENA_MARGIN < p2.x < S.WIDTH - S.ARENA_MARGIN, "posição fora da arena")
    check(not p2.can_be_hit(), "revivido deveria estar invulnerável")
    # acionamento único: segurar/repetir sem nova pressão não doa de novo; sem alvo não consome
    p1.lives = 5
    P("p1_donate_life")
    tick(g, 20, shield=False)
    check(p1.lives == 5, "doação sem aliado caído consumiu vida")
    # doação para si mesmo / de eliminado: eliminado não é doador
    eliminate(g, p1)
    P("p1_donate_life")
    check(p1.eliminated and p2.lives == 1, "eliminado não pode doar nem doar para si")
    # revivido pode cair de novo e voltar a ser alvo
    p2.invuln = 0
    p2.take_hit(force=True)
    check(p2.eliminated and p2.eliminated_at >= p1.eliminated_at, "ordem de eliminação não atualizou")
    # todos eliminados => fim de partida
    check(g.state == "gameover", "todos eliminados deveria encerrar a partida")


def test_doacao_multiplos_jogadores():
    g = mk(4)
    p1, p2, p3, p4 = g.players
    P = lambda *a: tick(g, 1, press=a, shield=False)
    eliminate(g, p2)
    tick(g, 30, shield=False)
    eliminate(g, p3)                      # p3 morreu DEPOIS: tem prioridade
    check(p3.eliminated_at > p2.eliminated_at, "eliminated_at deveria crescer")
    p1.lives, p4.lives = 3, 3
    # um doador só: revive o mais recente (p3), p2 segue caído
    P("p1_donate_life")
    check(p3.active and p2.eliminated and p1.lives == 2, "deveria reviver o mais recente primeiro")
    # dois doadores no MESMO quadro: nunca reviver o mesmo aliado duas vezes
    eliminate(g, p3)
    tick(g, 30, shield=False)
    p1.lives, p4.lives = 3, 3
    P("p1_donate_life", "p4_donate_life")
    check(p2.active and p3.active, "dois doadores deveriam reviver dois aliados diferentes")
    check(p1.lives + p4.lives == 4, f"cada doador paga 1 vida (total {p1.lives + p4.lives})")
    # com um doador sem vidas suficientes e outro com: só 1 doação
    eliminate(g, p2)
    eliminate(g, p3)
    tick(g, 30, shield=False)
    p1.lives, p4.lives = 1, 2
    P("p1_donate_life", "p4_donate_life")
    check(p4.lives == 1 and sum(1 for p in g.players if p.eliminated) == 1, "só o doador elegível deveria doar")
    # revive em posição segura: coloca uma bomba exatamente no ponto padrão e confere que escolheu outro x
    victim = next(p for p in g.players if p.eliminated)
    home = victim.cfg["spawn_x_frac"] * S.WIDTH
    g.spawn_hostile("bomb", home, S.GROUND_Y - 40, vy=0.0)
    g.spawn_hostile("bomb", home + 30, S.GROUND_Y - 50, vy=0.0)
    safe = g._safe_spawn_x(victim)
    check(abs(safe - home) > 80, f"posição de renascimento deveria evitar ameaças (home {home:.0f}, safe {safe:.0f})")


def test_doacao_com_hazards_e_pausa():
    g = mk(3)
    p1, p2, p3 = g.players
    eliminate(g, p3)
    to_combat(g, 6)
    kill_enemies(g)
    until(g, lambda: g.wave.state == "hazard")
    until(g, lambda: g.wave.hazards.stage == "run", limit=60 * 10)
    hz = g.wave.hazards
    # esfera/cápsula bem no ponto de renascimento padrão: o revive escolhe outro lugar
    safe = g._safe_spawn_x(p3)
    for (hx, hy, hr) in hz.threat_points():
        check(math.hypot(safe - hx, S.GROUND_Y - 30 - hy) > hr + 10, "renasceu dentro de um hazard")
    p1.lives = 3
    g.state = "paused"                                   # pausado: doação não é processada
    g.input.pressed.add("p1_donate_life")
    g.step(DT)
    check(p3.eliminated and p1.lives == 3, "doação processada durante a pausa")
    g.input.clear()
    g.state = "playing"
    tick(g, 1, press=("p1_donate_life",), shield=False)
    check(p3.active and p1.lives == 2, "doação durante fase de hazard falhou")


def test_sequencia_de_fases_todos_os_rounds():
    """Para cada round da tabela: combate limpo de hazards extras, serras desde o início, fases na ordem,
    cada fase só termina pela própria regra, round fecha no fim, serras saem."""
    for rnd in range(1, 10):
        g = mk(2, seed=100 + rnd)
        to_combat(g, rnd)
        plan = HZ.plan_for(rnd)
        c = hazard_counts(g)
        check(c["saws"] == plan["saws"], f"r{rnd}: serras no combate {c['saws']} != {plan['saws']}")
        check(c["rockets"] == c["pods"] == c["balls"] == c["spheres"] == 0, f"r{rnd}: hazards de fase junto do combate {c}")
        check(g.wave.state == "active" and len(g.wave.enemies) > 0, f"r{rnd}: combate não começou")
        for _ in range(60 * 6):                  # 6 s de combate: nenhuma fase de hazard pode nascer ou nem ser anunciada
            tick(g, 1)
            hz0 = g.wave.hazards
            c = hazard_counts(g)
            if not (c["rockets"] == c["pods"] == c["balls"] == c["spheres"] == 0 and not hz0.sequence_active
                    and hz0.stage == "idle" and g.wave.state == "active"):
                check(False, f"r{rnd}: fase de hazard apareceu durante o combate {c} stage={hz0.stage}")
                break
        kill_enemies(g)
        seen, saws_always = [], True
        last = None
        steps = 0
        while g.wave.state in ("active", "hazard") and steps < 60 * 400:
            hz = g.wave.hazards
            if hz.stage == "run" and hz.phase != last:
                seen.append(hz.phase)
            if hz.phase and hz.stage == "run":
                last = hz.phase
            elif hz.phase is None:
                last = None
            if g.wave.state == "hazard" and len(hz.saws) != plan["saws"]:
                saws_always = False
            # separação de fases: só os objetos da fase corrente existem
            if hz.stage in ("warn", "cleared"):
                pass
            counts = hazard_counts(g)
            if hz.phase == "rockets":
                check(counts["pods"] == counts["balls"] == counts["spheres"] == 0, f"r{rnd}: objetos de outra fase em rockets")
            if hz.phase == "ball_pod":
                check(counts["rockets"] == counts["spheres"] == 0, f"r{rnd}: objetos de outra fase em ball_pod")
            if hz.phase == "spheres":
                check(counts["rockets"] == counts["pods"] == counts["balls"] == 0, f"r{rnd}: objetos de outra fase em spheres")
            # "jogador" destrói o que for obrigatório depois de 1.5s de fase (por tiro real)
            if hz.stage == "run" and hz.phase in ("ball_pod", "spheres") and hz.phase_t > 1.5:
                for h in list(hz.pods) + list(hz.balls) + list(hz.spheres):
                    if h.alive and h.shootable:
                        h.x, h.y = 600.0, 400.0
                        h.hb = h._calc_hb()
                        g.players[0].x = 600.0
                        shoot_up(g, g.players[0], 600.0, 420.0, dmg=99.0)
                        break
            tick(g, 1)
            steps += 1
        check(g.wave.state == "clear", f"r{rnd}: round não fechou (estado {g.wave.state}, fase {g.wave.hazards.phase}/{g.wave.hazards.stage})")
        check(seen == EXPECTED_ORDER[rnd], f"r{rnd}: ordem das fases {seen} != {EXPECTED_ORDER[rnd]}")
        check(saws_always, f"r{rnd}: serras sumiram durante as fases")
        check(hazard_counts(g) == dict(saws=0, rockets=0, pods=0, balls=0, spheres=0), f"r{rnd}: sobrou hazard no round fechado {hazard_counts(g)}")
    print("      ordens verificadas nos rounds 1-9")


def test_round10_e_modo_infinito():
    check(HZ.plan_for(10)["order"] == () and HZ.plan_for(10)["saws"] == 0, "round 10 deveria vir sem hazards por padrão")
    for n in range(11, 41):
        p = HZ.plan_for(n)
        check(p["scale"] <= S.HAZARD_ENDLESS_MAX_SCALE and p["saws"] <= 4, f"plano infinito r{n} fora dos limites")
    check(HZ.plan_for(30)["scale"] > HZ.plan_for(11)["scale"], "infinito deveria escalar")
    # round 10 com chefe final: sem hazards, round fecha normalmente depois do chefe
    g = mk(2)
    to_combat(g, 10)
    check(hazard_counts(g)["saws"] == 0, "serras no chefe final")
    check(any(e.is_boss for e in g.wave.enemies), "chefe final ausente")
    tick(g, 120)
    kill_enemies(g)
    tick(g, 3)
    check(g.wave.state == "clear" or g.state == "gameover", f"round 10 não fechou ({g.wave.state})")
    # configurável: ligar hazards no round 10 não quebra a mecânica do chefe
    S.HAZARD_ROUNDS[10] = dict(saws=1, order=("rockets",), rockets=dict(duration=3.0, interval=(0.5, 0.8), max_alive=2, mix=(("small", 1),)))
    try:
        g = mk(2)
        to_combat(g, 10)
        check(hazard_counts(g)["saws"] == 1, "config do round 10 não foi respeitada")
        kill_enemies(g)
        until(g, lambda: g.wave.state in ("clear",) or g.state == "gameover", limit=60 * 60)
        check(g.wave.state == "clear" or g.state == "gameover", "round 10 com hazards não fechou")
    finally:
        S.HAZARD_ROUNDS[10] = dict(saws=0, order=())


def test_foguetes():
    g = mk(2)
    p1, p2 = g.players
    to_combat(g, 1)
    kill_enemies(g)
    until(g, lambda: g.wave.hazards.stage == "run", limit=60 * 10)
    hz = g.wave.hazards
    check(g.wave.state == "hazard" and hz.phase == "rockets", "fase de foguetes não iniciou")
    # fase só termina por tempo + resolução
    until(g, lambda: len(hz.rockets) >= 2, limit=60 * 15)
    until(g, lambda: hz.stage != "run", limit=60 * 40)
    check(hz.stage in ("resolve", "cleared") or hz.phase is None, "chuva não terminou por tempo")
    check(abs(hz.run_t - S.HAZARD_ROUNDS[1]["rockets"]["duration"]) < 0.2, f"duração da chuva {hz.run_t:.2f}s")
    tick(g, 30)
    check(all(r.state in ("fall", "fuse") for r in hz.rockets), "estado inesperado de foguete")
    # depois do tempo nenhum foguete NOVO nasce
    ids = {id(r) for r in hz.rockets}
    tick(g, 120)
    check(all(id(r) in ids for r in hz.rockets), "nasceu foguete depois do fim da chuva")
    until(g, lambda: g.wave.state == "clear", limit=60 * 40)
    check(g.wave.state == "clear", "round não fechou depois de resolver as explosões")

    # --- mecânica individual
    g = mk(2)
    p1, p2 = g.players
    to_combat(g, 3)
    kill_enemies(g)
    until(g, lambda: g.wave.hazards.stage == "run", limit=60 * 10)
    hz = g.wave.hazards
    hz.spawn_t = 10 ** 6                               # trava o gerador: controlamos os foguetes à mão
    hz.rockets.clear()
    hz.saws.clear()                                    # isola: a serra do round 3 também feriria os jogadores
    p1.x, p2.x = 300.0, 1000.0
    # 1) tamanhos/variações
    rs = {t: HZ.Rocket(hz, t, 640.0, 0.0, sum(S.ROCKET_TYPES[t]["speed"]) / 2) for t in S.ROCKET_TYPES}
    check(rs["small"].hp < rs["medium"].hp < rs["large"].hp, "hp deveria crescer com o tamanho")
    check(rs["small"].vy > rs["medium"].vy > rs["large"].vy, "pequeno deveria ser mais rápido")
    check(rs["small"].ground_radius < rs["medium"].ground_radius < rs["large"].ground_radius, "raio deveria crescer")
    # 2) destruído no ar por tiro real: explosão pequena, 1 vez só, pontua
    r = HZ.Rocket(hz, "medium", 640.0, 0.0, 300.0)
    r.y = 300.0
    r.hb = r._calc_hb()
    hz.rockets.append(r)
    score0 = p1.score
    for _ in range(2):
        shoot_up(g, p1, 640.0, 330.0)
        tick(g, 1)
        if not r.alive:
            break
    check(not r.alive and r.exploded, f"foguete não foi destruído no ar (hp {r.hp})")
    check(p1.score == score0 + r.points, "pontuação do foguete")
    check(p1.kills_by_type.get("rocket") == 1, "kills_by_type rocket")
    # 3) no chão: arma o pavio, detona depois, dano só dentro do raio
    r2 = HZ.Rocket(hz, "large", 300.0, 0.0, 300.0)
    r2.y = S.GROUND_Y - 100
    r2.hb = r2._calc_hb()
    hz.rockets.append(r2)
    p1.effects.clear(); p2.effects.clear()
    p1.invuln = p2.invuln = 0.0
    p1.x, p1.y = 300.0 + 40, float(S.GROUND_Y)            # dentro do raio 135
    p2.x, p2.y = 1000.0, float(S.GROUND_Y)                # longe
    lives1, lives2 = p1.lives, p2.lives
    tick(g, 20, shield=False)
    check(r2.state == "fuse" and r2.alive, f"foguete deveria estar armado no chão ({r2.state})")
    check(abs(r2.y + r2.h / 2 - S.GROUND_Y) < 1.5, "foguete não parou no chão")
    check(g.wave.state == "hazard", "foguete no chão não pode encerrar/derrubar a fase")
    check(p1.lives == lives1, "dano antes do pavio acabar")
    p1.x = 340.0
    until(g, lambda: not r2.alive, limit=60 * 3, shield=False)
    check(r2.exploded and not r2.alive, "foguete não detonou")
    check(p1.lives == lives1 - 1, f"p1 dentro do raio deveria perder 1 vida ({lives1}->{p1.lives})")
    check(p2.lives == lives2, "p2 fora do raio não pode perder vida")
    # 4) dano uma única vez por explosão
    tick(g, 10, shield=False)
    check(p1.lives == lives1 - 1, "dano repetido da mesma explosão")
    # 5) contato direto com jogador em queda
    p2.invuln = 0.0
    r3 = HZ.Rocket(hz, "small", 1000.0, 0.0, 400.0)
    r3.y = S.GROUND_Y - 80
    r3.hb = r3._calc_hb()
    hz.rockets.append(r3)
    l2 = p2.lives
    tick(g, 12, shield=False)
    check(not r3.alive and p2.lives == l2 - 1, f"contato com foguete deveria ferir 1x ({l2}->{p2.lives})")
    # 6) shield protege
    p2.invuln = 0.0
    p2.effects["shield"] = 5.0
    r4 = HZ.Rocket(hz, "small", 1000.0, 0.0, 400.0)
    r4.y = S.GROUND_Y - 80
    r4.hb = r4._calc_hb()
    hz.rockets.append(r4)
    l2 = p2.lives
    tick(g, 12, shield=False)
    check(p2.lives == l2, "escudo deveria proteger do foguete")


def test_ball_pod():
    g = mk(2)
    p1, p2 = g.players
    to_combat(g, 5)
    kill_enemies(g)
    until(g, lambda: g.wave.hazards.stage == "run", limit=60 * 20)
    hz = g.wave.hazards
    check(hz.phase == "ball_pod", "fase ball_pod não iniciou")
    until(g, lambda: len(hz.pods) == 2, limit=60 * 10)
    check({p.variant for p in hz.pods} == {"release", "bounce"}, "as duas variações deveriam existir")
    rel = next(p for p in hz.pods if p.variant == "release")
    bnc = next(p for p in hz.pods if p.variant == "bounce")
    # release: desce, arma, abre e libera
    check(rel.state == "descend" and rel.y < rel.target_y, "release deveria descer")
    until(g, lambda: rel.state == "arm", limit=60 * 15)
    check(rel.state == "arm", "release não chegou à posição de ativação")
    check(abs(rel.y - rel.target_y) < 2, "posição de ativação")
    until(g, lambda: rel.state == "open", limit=60 * 5)
    check(rel.state == "open" and 0.0 <= rel.open_k <= 1.0, "animação de abertura")
    n_before = len(hz.balls)
    until(g, lambda: rel.state == "spent", limit=60 * 5)
    lo, hi = S.BALL_POD_TYPES["release"]["balls"]
    got = len(hz.balls) - n_before
    check(lo <= got <= hi, f"liberou {got} esferas (esperado {lo}-{hi})")
    check(all(b.mandatory and b.alive for b in hz.balls), "esferas liberadas deveriam ser obrigatórias")
    until(g, lambda: not rel.alive, limit=60 * 3)
    check(not rel.alive, "casca da cápsula aberta deveria sumir")
    # mini-esferas se movem, quicam, ficam dentro da arena e causam dano 1x
    for _ in range(240):
        tick(g, 1)
        for b in hz.balls:
            check(-1 <= b.x - b.r and b.x + b.r <= S.WIDTH + 1 and b.y + b.r <= S.GROUND_Y + 1, "mini-esfera fora da arena")
    check(any(b.y + b.r > S.GROUND_Y - 4 or b.vy != 0 for b in hz.balls), "mini-esferas imóveis")
    ball = hz.balls[0]
    p1.invuln = 0.0
    p1.effects.clear()
    p1.x, p1.y = ball.x, float(S.GROUND_Y)
    ball.y = S.GROUND_Y - 30
    ball.hb = ball._calc_hb()
    l1 = p1.lives
    tick(g, 3, shield=False)
    check(p1.lives == l1 - 1, f"contato com mini-esfera deveria ferir 1x ({l1}->{p1.lives})")
    p1.effects["shield"] = 999
    # bounce: continua fechada, reflete nas bordas, alterna horizontal/diagonal
    modes, xs_seen = set(), []
    for _ in range(60 * 14):
        tick(g, 1)
        if bnc.alive:
            modes.add(bnc.mode)
            xs_seen.append(bnc.x)
            check(bnc.r - 1 <= bnc.x <= S.WIDTH - bnc.r + 1 and bnc.r + S.HUD_H - 1 <= bnc.y <= S.GROUND_Y - bnc.r + 1,
                  f"cápsula ricocheteante saiu da arena ({bnc.x:.0f},{bnc.y:.0f})")
            if bnc.state != "bounce":
                check(False, "cápsula ricocheteante não deveria abrir")
                break
    check(modes == {"h", "d"}, f"deveria alternar horizontal/diagonal ({modes})")
    check(max(xs_seen) > S.WIDTH - 120 and min(xs_seen) < 120, "cápsula não cobriu a arena de parede a parede")
    # fase NÃO termina enquanto houver cápsulas/esferas obrigatórias
    check(g.wave.hazards.phase == "ball_pod" and g.wave.state == "hazard", "fase terminou com ameaça pendente")
    # destruir a cápsula "release" antes de ativar: sem liberar nada
    g2 = mk(2)
    to_combat(g2, 5)
    kill_enemies(g2)
    until(g2, lambda: len(g2.wave.hazards.pods) >= 1 and g2.wave.hazards.stage == "run", limit=60 * 20)
    pod = next(p for p in g2.wave.hazards.pods if p.variant == "release")
    pod.y = 300.0
    pod.state = "descend"
    pod.target_y = 900.0
    pod.hb = pod._calc_hb()
    g2.players[0].x = pod.x
    for _ in range(10):
        shoot_up(g2, g2.players[0], pod.x, 330.0)
        tick(g2, 1)
        if not pod.alive:
            break
    check(not pod.alive and len(g2.wave.hazards.balls) == 0, "cápsula destruída antes de ativar não pode liberar esferas")
    check(g2.players[0].kills_by_type.get("pod") == 1, "kills_by_type pod")


def test_esferas_saltitantes():
    g = mk(2)
    p1, p2 = g.players
    to_combat(g, 8)
    kill_enemies(g)
    until(g, lambda: g.wave.hazards.stage == "run", limit=60 * 20)
    hz = g.wave.hazards
    check(hz.phase == "spheres" and hz.rockets == [] and hz.pods == [], "fase de esferas")
    until(g, lambda: not hz.queue, limit=60 * 20)
    n_expected = sum(c for _, c in S.HAZARD_ROUNDS[8]["spheres"]["mix"])
    n_expected = int(round(sum(max(1, int(round(c * hz.total_scale()))) for _, c in S.HAZARD_ROUNDS[8]["spheres"]["mix"])))
    check(len(hz.spheres) == n_expected, f"{len(hz.spheres)} esferas, esperado {n_expected}")
    kinds = {s.cfg["r"] for s in hz.spheres}
    check(len(kinds) == 2, "deveria haver tamanhos diferentes (leve/pesada)")
    light = next(s for s in hz.spheres if s.cfg is S.SPHERE_TYPES["light"])
    heavy = next(s for s in hz.spheres if s.cfg is S.SPHERE_TYPES["heavy"])
    check(light.hp < heavy.hp and light.r < heavy.r, "leve deveria ser menor e mais frágil")
    # física: gravidade, quique no chão, inversão nas paredes, alturas diferentes
    apex = {id(light): 10 ** 9, id(heavy): 10 ** 9}
    wall_flips = {id(light): 0, id(heavy): 0}
    bounces = {id(light): 0, id(heavy): 0}
    prev = {id(s): (s.vx, s.vy) for s in (light, heavy)}
    for _ in range(60 * 25):
        tick(g, 1)
        for s in (light, heavy):
            if not s.alive:
                continue
            check(s.x - s.r >= -1 and s.x + s.r <= S.WIDTH + 1 and s.y + s.r <= S.GROUND_Y + 1 and s.y - s.r >= S.HUD_H - 1,
                  f"esfera fora da arena ({s.x:.0f},{s.y:.0f})")
            pvx, pvy = prev[id(s)]
            if pvx * s.vx < 0:
                wall_flips[id(s)] += 1
            if pvy > 0 and s.vy < 0 and s.y + s.r > S.GROUND_Y - 6:
                bounces[id(s)] += 1
            if s.y + s.r < S.GROUND_Y - 100:
                apex[id(s)] = min(apex[id(s)], s.y)
            prev[id(s)] = (s.vx, s.vy)
    check(wall_flips[id(light)] >= 2 and wall_flips[id(heavy)] >= 1, f"inversão nas paredes {wall_flips}")
    check(bounces[id(light)] >= 5 and bounces[id(heavy)] >= 5, f"quiques no chão {bounces}")
    h_light = S.GROUND_Y - light.r - apex[id(light)]
    h_heavy = S.GROUND_Y - heavy.r - apex[id(heavy)]
    check(h_light > h_heavy + 60, f"leve deveria quicar mais alto ({h_light:.0f} vs {h_heavy:.0f})")
    # contato: dano 1x e a esfera continua
    p1.effects.clear(); p1.invuln = 0.0
    p1.x, p1.y = light.x, float(S.GROUND_Y)
    light.y = S.GROUND_Y - 40
    light.hb = light._calc_hb()
    l1 = p1.lives
    tick(g, 3, shield=False)
    check(p1.lives == l1 - 1 and light.alive, f"contato com esfera ({l1}->{p1.lives})")
    p1.effects["shield"] = 999
    # a fase NÃO termina por tempo
    tick(g, 60 * 5)
    check(g.wave.state == "hazard" and hz.phase == "spheres", "fase de esferas terminou sem destruir todas")
    # destruição por tiro real, uma a uma; a lista é limpa e a fase só fecha com a última
    alive = [s for s in hz.spheres if s.alive]
    for i, s in enumerate(alive):
        s.x, s.y, s.vx, s.vy = 640.0, 400.0, 0.0, 0.0
        s.hb = s._calc_hb()
        p1.x = 640.0
        score0 = p1.score
        for _ in range(12):
            shoot_up(g, p1, 640.0, 440.0, dmg=1.0)
            tick(g, 1)
            if not s.alive:
                break
        check(not s.alive, f"esfera {i} não foi destruída (hp {s.hp})")
        check(p1.score > score0, "pontuação da esfera")
        if i < len(alive) - 1:
            check(g.wave.state == "hazard" and hz.phase == "spheres", "fase terminou antes da última esfera")
    until(g, lambda: g.wave.state == "clear", limit=60 * 10)
    check(g.wave.state == "clear", "round não fechou depois da última esfera")
    check(hz.spheres == [], "esferas destruídas ainda estão na lista")

    # --- robustez: esfera sumida/corrompida não prende o jogo
    g = mk(2)
    to_combat(g, 8)
    kill_enemies(g)
    until(g, lambda: g.wave.hazards.stage == "run" and not g.wave.hazards.queue and g.wave.hazards.spheres, limit=60 * 20)
    hz = g.wave.hazards
    hz.spheres[0].x = float("nan")
    hz.spheres[1].x = 10 ** 7
    for s in hz.spheres[2:]:
        s.alive = False                                 # destruída "por fora": não pode ser contada
    tick(g, 3)
    check(len(hz.spheres) == 0 or all(s.alive for s in hz.spheres), "lista deveria estar limpa de inválidos")
    until(g, lambda: g.wave.state == "clear", limit=60 * 10)
    check(g.wave.state == "clear", "fase ficou presa esperando objeto inexistente")
    # trava de segurança por tempo
    g = mk(2)
    to_combat(g, 8)
    kill_enemies(g)
    until(g, lambda: g.wave.hazards.stage == "run" and g.wave.hazards.spheres, limit=60 * 20)
    g.wave.hazards.phase_t = S.HAZARD_PHASE_TIMEOUT + 1
    tick(g, 2)
    until(g, lambda: g.wave.state == "clear", limit=60 * 10)
    check(g.wave.state == "clear", "trava de segurança de fase não funcionou")


def test_serras():
    path = HZ._RailPath()
    # trilho contínuo e suave, cobre as 4 laterais
    pts = [path.point(s) for s in [i * 2.0 for i in range(int(path.length / 2) + 2)]]
    jumps = [math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1)]
    check(max(jumps) < 2.0 + 1e-6, f"salto no trilho ({max(jumps):.2f})")
    check(math.hypot(path.point(0)[0] - path.point(path.length)[0], path.point(0)[1] - path.point(path.length)[1]) < 1e-6, "trilho não fecha")
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    check(min(xs) <= path.l + 0.5 and max(xs) >= path.rr - 0.5 and min(ys) <= path.t + 0.5 and max(ys) >= path.b - 0.5, "trilho não passa pelas 4 laterais")
    check(path.b + S.BLACK_SAW["radius"] <= S.GROUND_Y + 3, "serra deveria rolar rente ao chão (não atravessar)")

    g = mk(2)
    p1, p2 = g.players
    to_combat(g, 9)
    hz = g.wave.hazards
    check(len(hz.saws) == 2, "round 9: 2 serras junto do combate")
    check(hz.saws[0].dir == -hz.saws[1].dir, "serras deveriam girar em sentidos opostos")
    s1 = hz.saws[0]
    # armada só depois do aviso de nascimento
    check(not s1.armed, "serra deveria nascer desarmada (telegrafada)")
    p1.effects.clear(); p1.invuln = 0.0
    p1.x, p1.y = s1.x, float(S.GROUND_Y)
    s1.y = S.GROUND_Y - 20
    l1 = p1.lives
    tick(g, 5, shield=False)
    check(p1.lives == l1 and not s1.armed, "serra desarmada não pode ferir")
    p1.x = 100.0
    until(g, lambda: s1.armed, limit=60 * 5)
    check(s1.armed, "serra não armou")
    # percorre o perímetro: volta completa
    s_start = s1.s
    angle0 = s1.angle
    seen_sides = set()
    for _ in range(int(60 * (path.length / S.BLACK_SAW["speed"] + 3))):
        tick(g, 1)
        x, y = s1.x, s1.y
        if x < path.l + 2: seen_sides.add("L")
        if x > path.rr - 2: seen_sides.add("R")
        if y < path.t + 2: seen_sides.add("T")
        if y > path.b - 2: seen_sides.add("B")
    check(seen_sides == {"L", "R", "T", "B"}, f"volta de 360°: lados vistos {seen_sides}")
    check(abs(s1.s - s_start) >= path.length * 0.9, "serra deveria completar uma volta")
    check(abs(s1.angle - angle0) > 5, "rotação visual parada")
    # tiros não afetam serra (indestrutível por padrão) e ela não entra nos alvos
    check(s1 not in hz.shootables(), "serra indestrutível não deveria ser alvo de tiro")
    # dano em contato: jogador no chão com a serra passando; só 1 vida; depois invulnerável
    p1.effects.clear(); p1.invuln = 0.0
    s1.s = 0.0
    # força a serra para o trecho da base
    s1.s = path.A + path.arc + path.B + path.arc + path.A * 0.5
    s1.x, s1.y = path.point(s1.s)
    p1.x, p1.y = s1.x, float(S.GROUND_Y)
    l1 = p1.lives
    tick(g, 2, shield=False)
    check(p1.lives == l1 - 1, f"serra deveria ferir ({l1}->{p1.lives})")
    tick(g, 5, shield=False)
    check(p1.lives == l1 - 1, "serra feriu de novo no mesmo evento")
    # pulo desvia: jogador no ar acima da serra não é ferido
    g.players[1].effects.clear(); g.players[1].invuln = 0.0
    s2 = hz.saws[1]
    s2.s = path.A + path.arc + path.B + path.arc + path.A * 0.5
    s2.x, s2.y = path.point(s2.s)
    s2.armed = True
    pj = g.players[1]
    pj.x, pj.y = s2.x, float(S.GROUND_Y - 130)
    l2 = pj.lives
    s2.dir = 0                                   # congela só para o teste de altura
    pj.vy = 0.0
    g.collisions.update()
    check(pj.lives == l2, "jogador pulando acima da serra não deveria ser ferido")
    s2.dir = -1
    # serras permanecem pelas fases e não bloqueiam a conclusão
    kill_enemies(g)
    until(g, lambda: g.wave.state == "hazard", limit=60 * 5)
    ids = {id(s) for s in hz.saws}
    for _ in range(60 * 3):
        tick(g, 1)
        check({id(s) for s in hz.saws} == ids, "serra removida durante as fases")
    # destrutível configurável
    S.BLACK_SAW["destructible"] = True
    try:
        g3 = mk(2)
        to_combat(g3, 3)
        sw = g3.wave.hazards.saws[0]
        until(g3, lambda: sw.armed, limit=60 * 5)
        check(sw in g3.wave.hazards.shootables(), "serra destrutível deveria ser alvo")
        sw.hp = 1.0
        g3.players[0].x = sw.x
        shoot_up(g3, g3.players[0], sw.x, sw.y + 10, dmg=5.0)
        tick(g3, 1)
        check(not sw.alive, "serra destrutível não morreu com tiro")
    finally:
        S.BLACK_SAW["destructible"] = False


def test_pausa_congela_hazards():
    g = mk(2)
    to_combat(g, 9)
    kill_enemies(g)
    until(g, lambda: g.wave.hazards.stage == "run", limit=60 * 10)
    hz = g.wave.hazards
    tick(g, 90)
    snap = (hz.run_t, hz.phase_t, hz.spawn_t, [(s.s, s.angle) for s in hz.saws],
            [(r.x, r.y, r.fuse) for r in hz.rockets], g.match_time)
    g.toggle_pause()
    check(g.state == "paused", "não pausou")
    for _ in range(600):
        g.input.update()
        g.step(DT)
    snap2 = (hz.run_t, hz.phase_t, hz.spawn_t, [(s.s, s.angle) for s in hz.saws],
             [(r.x, r.y, r.fuse) for r in hz.rockets], g.match_time)
    check(snap == snap2, "hazards/temporizadores avançaram durante a pausa")
    g.toggle_pause()
    check(g.state == "playing", "não despausou")
    tick(g, 30)
    check(hz.phase_t > snap[1], "hazards não retomaram depois da pausa")


def test_jogadores_1_a_4_e_morte_de_jogador():
    for n in (1, 2, 3, 4):
        g = mk(n, seed=40 + n)
        to_combat(g, 9)
        base_saws = len(g.wave.hazards.saws)
        check(base_saws == 2, f"{n}J: serras")
        kill_enemies(g)
        until(g, lambda: g.wave.hazards.stage == "run", limit=60 * 10)
        hz = g.wave.hazards
        check(abs(hz.player_scale() - (1 + S.HAZARD_PLAYER_SCALE * (n - 1))) < 1e-9, f"{n}J: escala por jogador")
        if n >= 2:
            eliminate(g, g.players[-1])                    # morte no meio da fase não interrompe nada
        if n >= 3:
            eliminate(g, g.players[-2])
        for _ in range(60 * 300):
            if g.wave.state != "hazard":
                break
            if g.state != "playing":
                break
            if hz.stage == "run" and hz.phase in ("ball_pod", "spheres") and hz.phase_t > 1.0:
                for h in list(hz.pods) + list(hz.balls) + list(hz.spheres):
                    if h.alive:
                        g.on_hazard_destroyed(h, g.players[0])
            tick(g, 1)
        check(g.wave.state == "clear", f"{n}J: round 9 não fechou ({g.wave.state}/{hz.phase})")
        check(g.state == "playing", f"{n}J: partida não deveria ter acabado")
    # mais jogadores => mais esferas
    counts = []
    for n in (1, 4):
        g = mk(n)
        to_combat(g, 8)
        kill_enemies(g)
        until(g, lambda: g.wave.hazards.stage == "run" and not g.wave.hazards.queue, limit=60 * 20)
        counts.append(len(g.wave.hazards.spheres))
    check(counts[1] > counts[0], f"4 jogadores deveria gerar mais esferas ({counts})")


def test_modo_infinito_dificuldades_e_boosts_globais():
    # modo infinito: rounds > 10 reciclam o ciclo de hazards e fecham normalmente
    for rnd in (11, 12, 13, 14, 15):
        g = mk(2, mode="endless", seed=rnd)
        to_combat(g, rnd)
        plan = HZ.plan_for(rnd)
        check(len(g.wave.hazards.saws) == plan["saws"], f"infinito r{rnd}: serras")
        kill_enemies(g)
        for _ in range(60 * 400):
            if g.wave.state != "hazard" and g.wave.state != "active":
                break
            hz = g.wave.hazards
            if hz.stage == "run" and hz.phase in ("ball_pod", "spheres") and hz.phase_t > 1.0:
                for h in list(hz.pods) + list(hz.balls) + list(hz.spheres):
                    if h.alive:
                        g.on_hazard_destroyed(h, g.players[0])
            tick(g, 1)
        check(g.wave.state == "clear", f"infinito r{rnd}: round não fechou ({g.wave.state})")
    # todas as dificuldades: hp/velocidade dos hazards escalam e nada quebra
    hp_seen = {}
    for diff in S.DIFFICULTY_ORDER:
        g = mk(2, difficulty=diff, seed=3)
        to_combat(g, 9)
        kill_enemies(g)
        until(g, lambda: g.wave.hazards.stage == "run", limit=60 * 10)
        hz = g.wave.hazards
        hp_seen[diff] = HZ.BouncingSphere(hz, "sphere", S.SPHERE_TYPES["heavy"], 500, 300, 0, 0, 0, 1, "#ff9a3c").hp
        for _ in range(60 * 300):
            if g.wave.state != "hazard":
                break
            if hz.stage == "run" and hz.phase in ("ball_pod", "spheres") and hz.phase_t > 1.0:
                for h in list(hz.pods) + list(hz.balls) + list(hz.spheres):
                    if h.alive:
                        g.on_hazard_destroyed(h, g.players[0])
            tick(g, 1)
        check(g.wave.state == "clear", f"dificuldade {diff}: round 9 não fechou")
    check(hp_seen["easy"] <= hp_seen["normal"] <= hp_seen["hard"] <= hp_seen["extreme"] and hp_seen["easy"] < hp_seen["extreme"],
          f"hp das esferas deveria crescer com a dificuldade {hp_seen}")
    # boost global "naves lentas" também desacelera os hazards; "naves rápidas" acelera
    g = mk(2, seed=11)
    to_combat(g, 8)
    hz = g.wave.hazards
    sw = hz.saws[0]
    until(g, lambda: sw.armed, limit=60 * 5)
    def speed_of(mult_key):
        g.global_effects.clear()
        if mult_key:
            g.global_effects[mult_key] = 99.0
        s0 = sw.s
        tick(g, 30)
        return abs(sw.s - s0)
    base, slow, fast = speed_of(None), speed_of("slow_foes"), speed_of("fast_foes")
    check(slow < base * 0.7 and fast > base * 1.2, f"boosts globais vs serra: lento {slow:.0f} normal {base:.0f} rápido {fast:.0f}")


def test_reinicio_e_saida_no_meio_da_fase():
    g = mk(3, seed=21)
    to_combat(g, 9)
    kill_enemies(g)
    until(g, lambda: g.wave.hazards.stage == "run", limit=60 * 10)
    tick(g, 120)
    check(g.wave.hazards.any_active(), "deveria haver hazards ativos")
    g.restart_match()
    hz = g.wave.hazards
    check(not hz.any_active() and hz.stage == "idle" and hz.plan is None and not hz.sequence_active, "restart deixou hazards/estado para trás")
    check(g.wave.round_no == 1 and g.match_time == 0.0 and g.life_drops_this_round == 0, "restart não zerou contadores")
    until(g, lambda: g.wave.state == "active", limit=60 * 20)
    check(hazard_counts(g)["saws"] == 0, "round 1 não tem serras")
    # voltar ao menu e iniciar outra partida
    to_combat(g, 9)
    check(len(g.wave.hazards.saws) == 2, "serras do round 9 depois de reiniciar")
    g.go_to_title()
    g.player_count = 2
    g.start_match()
    check(not g.wave.hazards.any_active(), "nova partida herdou hazards")
    # fim de jogo no meio de uma fase (todos eliminados) limpa o estado e a tela de resultado desenha
    to_combat(g, 6)
    kill_enemies(g)
    until(g, lambda: g.wave.hazards.stage == "run", limit=60 * 10)
    for p in g.players:
        eliminate(g, p)
    tick(g, 2, shield=False, draw=True)
    check(g.state == "gameover" and not g.victory, "derrota por eliminação total")
    for _ in range(30):
        g.input.update(); g.step(DT); g.draw(SCREEN)


def test_estado_transicoes_e_banners():
    g = mk(2)
    to_combat(g, 6)
    kill_enemies(g)
    titles = []
    for _ in range(60 * 200):
        if g.banner and (not titles or titles[-1] != g.banner["title"]):
            titles.append(g.banner["title"])
        hz = g.wave.hazards
        if hz.stage == "run" and hz.phase in ("ball_pod", "spheres") and hz.phase_t > 1.0:
            for h in list(hz.pods) + list(hz.balls) + list(hz.spheres):
                if h.alive:
                    g.on_hazard_destroyed(h, g.players[0])
        if g.wave.state == "clear":
            break
        tick(g, 1)
    want = ["BALL POD DEPLOYED!", "HAZARD CLEARED!", "BOUNCING SPHERES!", "HAZARD CLEARED!"]
    sub = [t for t in titles if t in want]
    check(sub == want, f"sequência de avisos {sub} != {want}")
    check(any("CONCLU" in t for t in titles), f"aviso de round concluído ausente: {titles}")
    check(g.banner is None or g.banner.get("compact") or "CONCLU" in g.banner["title"], "banner final inesperado")


def test_partida_completa_10_rounds():
    """Joga a partida clássica inteira com um 'bot' (mata inimigos, destrói hazards obrigatórios):
    tem que chegar à vitória passando por todos os rounds, chefes e fases extras, sem exceções."""
    g = mk(2, seed=2026)
    rounds_seen = []
    guard = 0
    while g.state == "playing" and guard < 60 * 3000:
        guard += 1
        w = g.wave
        if w.state == "active" and w.enemies and w.round_no not in rounds_seen:
            rounds_seen.append(w.round_no)
        if w.state == "active" and w.enemies and guard % 90 == 0:
            kill_enemies(g)
        hz = w.hazards
        if w.state == "hazard" and hz.stage == "run" and hz.phase in ("ball_pod", "spheres") and hz.phase_t > 1.0 and guard % 20 == 0:
            for h in list(hz.pods) + list(hz.balls) + list(hz.spheres):
                if h.alive:
                    g.on_hazard_destroyed(h, g.players[0])
                    break
        tick(g, 1)
    check(g.state == "gameover" and g.victory, f"deveria vencer a partida (estado {g.state}, round {g.wave.round_no})")
    check(rounds_seen == list(range(1, 11)), f"rounds jogados {rounds_seen}")


def test_desempenho_e_desenho():
    g = mk(4, seed=5)
    to_combat(g, 9)
    hz = g.wave.hazards
    # cena pesada: combate cheio + serras + (forçadas) todas as fases ao mesmo tempo SÓ para medir custo de desenho
    for _ in range(8):
        hz.rockets.append(HZ.Rocket(hz, random.choice(list(S.ROCKET_TYPES)), random.uniform(60, 1200), 0.0, 120.0))
        hz.rockets[-1].y = random.uniform(100, 600)
    for stype in ("light", "heavy", "light", "heavy", "light", "heavy"):
        hz._spawn_sphere(stype)
    for variant in ("release", "bounce", "bounce"):
        hz._spawn_pod(variant)
    pod = hz.pods[0]
    hz.release_balls(pod)
    for s in hz.saws:
        s.armed = True
    t0 = time.perf_counter()
    N = 300
    for _ in range(N):
        tick(g, 1, draw=True)
    ms = (time.perf_counter() - t0) / N * 1000
    n_obj = sum(hazard_counts(g).values())
    print(f"      {n_obj} hazards + {len(g.wave.enemies)} inimigos + 4 jogadores: {ms:.1f} ms/quadro (update+draw, headless)")
    check(ms < 33.0, f"quadro lento demais: {ms:.1f} ms")
    # sem vazamento de listas
    for _ in range(60 * 30):
        tick(g, 1)
    check(len(g.fx.items) <= S.MAX_PARTICLES + 20, f"acúmulo de partículas ({len(g.fx.items)})")
    for lst in (hz.rockets, hz.pods, hz.balls, hz.spheres):
        check(all(h.alive for h in lst), "objeto morto deixado na lista")
    os.makedirs("/tmp/shots", exist_ok=True)
    pygame.image.save(SCREEN, "/tmp/shots/hazards_scene.png")


# ============================================================================= MODO ROCKETS SKY
def test_rockets_sky_inicio_e_hud():
    g = mk(1, mode="rockets_sky", seed=11)
    check(g.mode_runner is not None, "mode_runner deveria existir em rockets_sky")
    check(g.mode_runner.mode_key == "rockets_sky", "mode_key incorreto")
    check(g.wave.state == "mode", f"WaveManager deveria estar em 'mode', está em {g.wave.state!r}")
    check(g.wave.hazards.phase == "rockets", "fase deveria ser 'rockets' desde o início")
    check(g.mode_runner.level == 1, "deveria começar no nível 1")
    lines = g.mode_runner.hud_lines()
    check(any("TEMPO" in t for t, _ in lines), f"HUD sem TEMPO: {lines}")
    check(any("NÍVEL" in t for t, _ in lines), f"HUD sem NÍVEL: {lines}")
    tick(g, 1, draw=True)     # garante que desenha sem estourar (HUD central + banner)


def test_rockets_sky_progressao_exata_por_tempo():
    """Teste 1 do design doc: a dificuldade sobe exatamente a cada 10s, nem antes nem depois."""
    g = mk(1, mode="rockets_sky", seed=12)
    mr = g.mode_runner
    check(mr.level == 1, "nível inicial deveria ser 1")
    tick(g, int(S.ROCKETS_SKY_LEVEL_INTERVAL * 60) - 2)
    check(mr.level == 1, f"não deveria ter subido de nível ainda (nível={mr.level})")
    tick(g, 3)
    check(mr.level == 2, f"deveria estar no nível 2 logo após 10s (nível={mr.level})")
    tick(g, int(S.ROCKETS_SKY_LEVEL_INTERVAL * 60) - 1)
    check(mr.level == 3, f"deveria estar no nível 3 após 20s (nível={mr.level})")


def test_rockets_sky_pausa_nao_avanca_timer():
    """Teste 2 do design doc: pausado, o contador de sobrevivência não deve avançar."""
    g = mk(1, mode="rockets_sky", seed=13)
    tick(g, 120)
    elapsed_before = g.mode_runner.elapsed
    level_before = g.mode_runner.level
    g.state = "paused"
    for _ in range(60 * 5):
        g.step(DT)
    check(g.mode_runner.elapsed == elapsed_before, "o tempo de sobrevivência avançou durante a pausa")
    check(g.mode_runner.level == level_before, "o nível subiu durante a pausa")
    g.state = "playing"
    tick(g, 60)
    check(g.mode_runner.elapsed > elapsed_before, "o tempo deveria voltar a avançar após despausar")


def test_rockets_sky_spawn_velocidade_e_quantidade_crescem():
    """Níveis mais altos devem permitir mais foguetes simultâneos e foguetes mais rápidos (seção 5.3)."""
    g = mk(2, mode="rockets_sky", seed=14)
    mr = g.mode_runner
    cfg_lvl1 = dict(mr.phase_cfg)
    mr.level = S.ROCKETS_SKY_LEVEL_SOFTCAP
    mr._apply_level_cfg()
    cfg_softcap = mr.phase_cfg
    check(cfg_softcap["max_alive"] >= cfg_lvl1["max_alive"],
          f"max_alive não deveria cair com o nível ({cfg_lvl1['max_alive']} -> {cfg_softcap['max_alive']})")
    check(cfg_softcap["speed_mult"] > cfg_lvl1["speed_mult"],
          f"speed_mult deveria crescer com o nível ({cfg_lvl1['speed_mult']} -> {cfg_softcap['speed_mult']})")
    check(cfg_softcap["interval"][1] <= cfg_lvl1["interval"][1],
          "intervalo entre foguetes deveria diminuir (ou igual) em níveis mais altos")
    # nunca "exploda": sempre dentro dos tetos configurados
    check(cfg_softcap["max_alive"] <= S.ROCKETS_SKY_MAX_ALIVE[1] + 1e-9, "max_alive estourou o teto")
    check(cfg_softcap["speed_mult"] <= S.ROCKETS_SKY_SPEED_MULT[1] + 1e-9, "speed_mult estourou o teto")
    # além do softcap, a dificuldade não deve continuar crescendo (progressão controlada, nunca explosiva)
    mr.level = S.ROCKETS_SKY_LEVEL_SOFTCAP + 5
    mr._apply_level_cfg()
    check(mr.phase_cfg["max_alive"] == cfg_softcap["max_alive"], "dificuldade não deveria crescer além do softcap")


def test_rockets_sky_foguetes_nascem_e_ferem():
    """Spawn real de foguetes ao longo do tempo, usando a física/colisão existente (Rocket/HazardManager)."""
    g = mk(2, mode="rockets_sky", seed=15)
    tick(g, 60 * 6, shield=False)       # 6s: tempo suficiente para vários foguetes nascerem e caírem
    check(len(g.wave.hazards.rockets) > 0, "nenhum foguete chegou a nascer em 6s")
    check(g.wave.cars == [] and g.wave.enemies == [], "rockets_sky não deveria ter inimigos/carros normais")


def test_rockets_sky_gameover_e_recorde():
    """Ciclo completo: jogador eliminado -> end_match -> recorde gravado (nunca pior que o anterior)."""
    g = mk(1, mode="rockets_sky", seed=16)
    tick(g, 30)
    p = g.players[0]
    p.effects.pop("shield", None)
    p.lives = 0
    p.eliminated = True
    g.on_player_eliminated(p)
    tick(g, 1)
    check(g.state == "gameover", f"deveria ter terminado a partida, estado={g.state!r}")
    check(g.mode_record_result is not None, "mode_record_result deveria estar preenchido")
    is_new, record = g.mode_record_result
    check(is_new is True, "primeiro resultado da sessão deveria virar recorde")
    check(record == g.mode_runner.elapsed, "o recorde gravado deveria ser o tempo sobrevivido")
    check(g.config.get_record("rockets_sky") == record, "recorde não refletido no ConfigManager")
    result = dict(g.mode_runner.result_lines())
    check("TEMPO DE SOBREVIVÊNCIA" in result, f"result_lines sem tempo: {result}")
    check("NÍVEL DO FOGUETE" in result, f"result_lines sem nível: {result}")
    check("MELHOR TEMPO" in result, f"result_lines sem melhor tempo: {result}")
    tick(g, int(S.GAMEOVER_INPUT_LOCK * 60) + 5, draw=True)   # garante que a tela de resultado desenha sem estourar


def test_rockets_sky_nao_quebra_classico_nem_endless():
    """Depois de existir o modo survival, o Clássico e o 50 Rounds continuam com WaveManager normal."""
    g = mk(2, mode="classic", seed=17)
    check(g.mode_runner is None, "Clássico não deveria ter mode_runner")
    check(g.wave.round_no == 1 and g.wave.state == "intro", "Clássico deveria começar no round 1 normalmente")
    to_combat(g, 1)
    check(g.wave.state == "active" and len(g.wave.enemies) > 0, "round 1 do Clássico sem inimigos")

    g2 = mk(2, mode="endless", seed=18)
    check(g2.mode_runner is None, "50 Rounds não deveria ter mode_runner")
    check(g2.rounds_to_win == S.GAME_MODES["endless"]["rounds_to_win"], "rounds_to_win do 50 Rounds incorreto")


# ============================================================================= MODO BALL RAIN
def destroy_all_hazards(g, killer=None):
    """Helper de teste: destrói (hit até a morte) todos os pods/esferas/mini-esferas vivos agora."""
    killer = killer or g.players[0]
    hz = g.wave.hazards
    n = 0
    for lst_name in ("pods", "spheres", "balls"):
        for h in list(getattr(hz, lst_name)):
            if h.alive and h.hp is not None:
                if h.hit(h.hp + 1):
                    g.on_hazard_destroyed(h, killer)
                    n += 1
    return n


def test_ball_rain_inicio_e_hud():
    g = mk(1, mode="ball_rain", seed=21)
    check(g.mode_runner is not None, "mode_runner deveria existir em ball_rain")
    check(g.mode_runner.mode_key == "ball_rain", "mode_key incorreto")
    check(g.wave.state == "mode", f"WaveManager deveria estar em 'mode', está em {g.wave.state!r}")
    check(g.mode_runner.round_no == 1, "deveria começar no round 1")
    check(g.wave.hazards.phase == "ball_pod", "round 1 deveria começar com ball_pod")
    tick(g, 1, draw=True)


def test_ball_rain_so_pods_antes_do_round_de_esferas():
    g = mk(1, mode="ball_rain", seed=22)
    mr = g.mode_runner
    for n in range(1, S.BALL_RAIN_SPHERES_START_ROUND):
        pods, spheres = mr._counts_for_round(n)
        check(spheres == 0, f"round {n} não deveria ter esferas ainda (spheres={spheres})")
        check(pods > 0, f"round {n} deveria ter ao menos 1 pod")
    pods, spheres = mr._counts_for_round(S.BALL_RAIN_SPHERES_START_ROUND)
    check(spheres > 0, "a partir de BALL_RAIN_SPHERES_START_ROUND deveria haver esferas")


def test_ball_rain_progressao_por_round():
    """Teste dedicado: destruir tudo avança o round, aumentando pods/esferas a cada vez (com teto)."""
    g = mk(2, mode="ball_rain", seed=23)
    g.players[0].invuln = g.players[1].invuln = 999.0
    seen_rounds = [1]
    for _ in range(60 * 90):
        tick(g, 1)
        destroy_all_hazards(g)
        if g.mode_runner.round_no != seen_rounds[-1]:
            seen_rounds.append(g.mode_runner.round_no)
        if len(seen_rounds) >= 6:
            break
    check(len(seen_rounds) >= 6, f"deveria ter avançado vários rounds, só chegou a {seen_rounds}")
    check(seen_rounds == sorted(seen_rounds), f"rounds deveriam ser sempre crescentes: {seen_rounds}")
    check(seen_rounds == list(range(1, len(seen_rounds) + 1)), f"rounds deveriam subir 1 a 1: {seen_rounds}")
    pods_r1, _ = g.mode_runner._counts_for_round(1)
    pods_r5, spheres_r5 = g.mode_runner._counts_for_round(5)
    check(pods_r5 >= pods_r1, "quantidade de pods não deveria cair com o round")
    check(pods_r5 <= S.BALL_RAIN_MAX_PODS, "pods estourou o teto")
    check(spheres_r5 <= S.BALL_RAIN_MAX_SPHERES, "esferas estourou o teto")


def test_ball_rain_velocidade_cresce_com_teto():
    g = mk(1, mode="ball_rain", seed=24)
    mr = g.mode_runner
    mult_r1 = mr._speed_mult_for_round(1)
    mult_mid = mr._speed_mult_for_round(20)
    mult_far = mr._speed_mult_for_round(200)
    check(mult_r1 == 1.0, f"round 1 deveria ter speed_mult 1.0, tem {mult_r1}")
    check(mult_mid > mult_r1, "velocidade deveria crescer com o round")
    check(mult_far <= S.BALL_RAIN_MAX_SPEED_MULT + 1e-9, "speed_mult nunca deveria estourar o teto")
    check(abs(mult_far - S.BALL_RAIN_MAX_SPEED_MULT) < 1e-6,
          "em round muito avançado, speed_mult deveria estar no teto")


def test_ball_rain_wave_plan_nao_corrompe_entre_rounds():
    """Regressão do bug: WaveManager não pode chamar _finish_round()/begin_round() por conta própria
    enquanto um ModeManager está ativo (isso sobrescrevia hz.plan com o plano do round 1 clássico)."""
    g = mk(1, mode="ball_rain", seed=25)
    g.players[0].invuln = 999.0
    for _ in range(60 * 30):
        tick(g, 1)
        destroy_all_hazards(g)
    check(g.wave.state == "mode", f"wave.state vazou para {g.wave.state!r} (deveria continuar 'mode')")
    order = g.wave.hazards.plan["order"] if g.wave.hazards.plan else ()
    check(set(order) <= {"ball_pod", "spheres"}, f"hz.plan deveria ser do Ball Rain, veio {order}")
    check(g.wave.round_no == 0, "WaveManager.round_no não deveria ter avançado (quem conta é o ModeManager)")


def test_ball_rain_gameover_e_recorde():
    g = mk(1, mode="ball_rain", seed=26)
    tick(g, 30)
    p = g.players[0]
    p.effects.pop("shield", None)
    p.lives = 0
    p.eliminated = True
    g.on_player_eliminated(p)
    tick(g, 1)
    check(g.state == "gameover", f"deveria ter terminado a partida, estado={g.state!r}")
    is_new, record = g.mode_record_result
    check(is_new is True, "primeiro resultado da sessão deveria virar recorde")
    check(record == g.mode_runner.round_no, "recorde deveria ser o round alcançado")
    check(g.config.get_record("ball_rain") == record, "recorde não refletido no ConfigManager")
    result = dict(g.mode_runner.result_lines())
    check("ROUND ALCANÇADO" in result and "MELHOR ROUND" in result, f"result_lines incompletas: {result}")
    tick(g, int(S.GAMEOVER_INPUT_LOCK * 60) + 5, draw=True)


def test_ball_rain_nao_quebra_classico_nem_rockets_sky():
    """Depois do Ball Rain existir, Clássico e Rockets Sky continuam funcionando como antes."""
    g = mk(2, mode="classic", seed=27)
    check(g.mode_runner is None, "Clássico não deveria ter mode_runner")
    to_combat(g, 5)       # round 5 do Clássico já tem ball_pod de verdade (HAZARD_ROUNDS)
    check(g.wave.state == "active", "Clássico deveria estar em combate normal no round 5")

    g2 = mk(1, mode="rockets_sky", seed=28)
    tick(g2, 60 * 11)
    check(g2.mode_runner.level == 2, f"Rockets Sky deveria seguir subindo de nível normalmente, nível={g2.mode_runner.level}")


# ============================================================================= MODO MECHANIC ROOM
def test_mechanic_room_inicio_e_hud():
    g = mk(1, mode="mechanic_room", seed=31)
    check(g.mode_runner is not None, "mode_runner deveria existir em mechanic_room")
    check(g.mode_runner.mode_key == "mechanic_room", "mode_key incorreto")
    check(g.wave.state == "mode", f"WaveManager deveria estar em 'mode', está em {g.wave.state!r}")
    check(g.mode_runner.wave_no == 1, "deveria começar na wave 1")
    check(g.wave.hazards.plan["cfg"]["ball_pod"]["pods"] == ("bounce",),
          f"wave 1 deveria ter exatamente 1 cápsula 'bounce': {g.wave.hazards.plan['cfg']['ball_pod']['pods']}")
    lines = g.mode_runner.hud_lines()
    check(any("WAVE" in t for t, _ in lines), f"HUD sem WAVE: {lines}")
    check(any("CÁPSULAS" in t and "PRÓXIMA" in t for t, _ in lines), f"HUD sem cápsulas/próxima: {lines}")
    check(any("TEMPO" in t for t, _ in lines), f"HUD sem TEMPO: {lines}")
    tick(g, 1, draw=True)


def test_mechanic_room_incremento_de_um_por_ciclo():
    """Seção 7.1: a cada ciclo concluído, +1 cápsula ricocheteante — nunca mais, nunca menos."""
    g = mk(1, mode="mechanic_room", seed=32)
    mr = g.mode_runner
    for n in range(1, 10):
        pods = mr._pods_for_wave(n)
        check(pods == S.MECHANIC_ROOM_INITIAL_PODS + (n - 1) * S.MECHANIC_ROOM_POD_INCREMENT,
              f"wave {n} deveria ter {S.MECHANIC_ROOM_INITIAL_PODS + (n - 1) * S.MECHANIC_ROOM_POD_INCREMENT} pods, calculou {pods}")
    check(mr._pods_for_wave(1) == 1, "wave 1 deveria ter exatamente 1 cápsula (seção 7.2: TARGET: 1)")
    check(mr._pods_for_wave(2) == 2, "wave 2 deveria ter exatamente 2 cápsulas (seção 7.2: TARGET: 2)")


def test_mechanic_room_sem_teto_de_quantidade():
    """Seção 7.2: 'não existe uma quantidade fixa máxima' para a contagem de cápsulas."""
    g = mk(1, mode="mechanic_room", seed=33)
    mr = g.mode_runner
    pods_100 = mr._pods_for_wave(100)
    pods_1000 = mr._pods_for_wave(1000)
    check(pods_1000 > pods_100, "a quantidade de cápsulas não deveria ter teto (deve continuar subindo)")
    check(pods_1000 == S.MECHANIC_ROOM_INITIAL_PODS + 999 * S.MECHANIC_ROOM_POD_INCREMENT,
          "a fórmula de quantidade de cápsulas não deveria saturar em nenhum nível")


def test_mechanic_room_velocidade_e_quique_tem_teto():
    """Seção 7.4: velocidade e intensidade do quique aumentam, mas com teto (diferente da quantidade)."""
    g = mk(1, mode="mechanic_room", seed=34)
    mr = g.mode_runner
    check(mr._speed_mult_for_wave(1) == 1.0, "wave 1 deveria ter speed_mult 1.0")
    check(mr._bounce_mult_for_wave(1) == 1.0, "wave 1 deveria ter bounce_mult 1.0")
    check(mr._speed_mult_for_wave(500) <= S.MECHANIC_ROOM_MAX_SPEED_MULT + 1e-9, "speed_mult estourou o teto")
    check(mr._bounce_mult_for_wave(500) <= S.MECHANIC_ROOM_MAX_BOUNCE_MULT + 1e-9, "bounce_mult estourou o teto")
    check(mr._speed_mult_for_wave(50) > mr._speed_mult_for_wave(10), "velocidade deveria crescer com a wave")
    check(mr._bounce_mult_for_wave(50) > mr._bounce_mult_for_wave(10), "intensidade do quique deveria crescer com a wave")


def test_mechanic_room_progressao_real_destruindo_capsulas():
    """Ciclo completo de verdade: destruir todas as cápsulas de uma wave avança para a próxima,
    sempre 1 a 1, limpando corretamente os objetos antigos (seção 7.3)."""
    g = mk(1, mode="mechanic_room", seed=35)
    g.players[0].invuln = 999.0
    waves_seen = [1]
    for _ in range(60 * 60):
        tick(g, 1)
        destroy_all_hazards(g)
        if g.mode_runner.wave_no != waves_seen[-1]:
            waves_seen.append(g.mode_runner.wave_no)
        if len(waves_seen) >= 5:
            break
    check(waves_seen == list(range(1, len(waves_seen) + 1)), f"waves deveriam subir 1 a 1: {waves_seen}")
    check(g.wave.hazards.pods == [] or all(p.alive for p in g.wave.hazards.pods),
          "não deveria sobrar cápsula morta não removida (limpeza correta dos objetos antigos)")


def test_mechanic_room_contagem_de_capsulas_destruidas():
    """Seção 7.6: quantidade total de esferas/cápsulas destruídas deve ser registrada corretamente."""
    g = mk(1, mode="mechanic_room", seed=36)
    g.players[0].invuln = 999.0
    p = g.players[0]
    check(p.kills_by_type.get("pod", 0) == 0, "deveria começar com 0 cápsulas destruídas")
    destroyed_total = 0
    for _ in range(60 * 40):
        tick(g, 1)
        destroyed_total += destroy_all_hazards(g, killer=p)
        if g.mode_runner.wave_no >= 4:
            break
    check(p.kills_by_type.get("pod", 0) == destroyed_total,
          f"contagem de cápsulas destruídas incorreta: {p.kills_by_type.get('pod', 0)} vs {destroyed_total}")
    result = dict(g.mode_runner.result_lines())
    check(result["CÁPSULAS DESTRUÍDAS"] == str(destroyed_total), f"result_lines não bate: {result}")


def test_mechanic_room_gameover_e_recorde():
    g = mk(1, mode="mechanic_room", seed=37)
    tick(g, 30)
    p = g.players[0]
    p.effects.pop("shield", None)
    p.lives = 0
    p.eliminated = True
    g.on_player_eliminated(p)
    tick(g, 1)
    check(g.state == "gameover", f"deveria ter terminado a partida, estado={g.state!r}")
    is_new, record = g.mode_record_result
    check(is_new is True, "primeiro resultado da sessão deveria virar recorde")
    check(record == g.mode_runner.wave_no, "recorde deveria ser a wave alcançada")
    check(g.config.get_record("mechanic_room") == record, "recorde não refletido no ConfigManager")
    result = dict(g.mode_runner.result_lines())
    for key in ("MAIOR WAVE ALCANÇADA", "TEMPO SOBREVIVIDO", "CÁPSULAS DESTRUÍDAS", "MELHOR WAVE"):
        check(key in result, f"result_lines sem {key}: {result}")
    tick(g, int(S.GAMEOVER_INPUT_LOCK * 60) + 5, draw=True)


def test_mechanic_room_nao_quebra_outros_modos():
    g = mk(2, mode="classic", seed=38)
    check(g.mode_runner is None, "Clássico não deveria ter mode_runner")
    to_combat(g, 1)
    check(g.wave.state == "active" and len(g.wave.enemies) > 0, "round 1 do Clássico sem inimigos")

    g2 = mk(1, mode="ball_rain", seed=39)
    tick(g2, 30)
    check(g2.mode_runner.round_no == 1, "Ball Rain deveria continuar funcionando normalmente")

    g3 = mk(1, mode="rockets_sky", seed=40)
    tick(g3, 30)
    check(g3.mode_runner.level == 1, "Rockets Sky deveria continuar funcionando normalmente")


# ============================================================================= MODO CRAZY CAR
def defeat_car(g, killer=None, max_frames=600):
    """Helper de teste: pula no carro atual repetidamente (stomp real, respeitando stomp_lock) até ele
    morrer. Dá mais 1 quadro após a morte para o CrazyCarMode.update() detectar isso e criar o carro
    do próximo nível (_on_car_defeated/_spawn_car só rodam no próximo game.step(), nunca dentro do
    próprio on_stomp) — assim quem chama este helper já lê g.mode_runner.car como o carro NOVO.
    Checa car.alive diretamente: game.on_stomp() não repassa o retorno de car.stomp() para fora, então
    não dá para confiar no valor de retorno de on_stomp aqui. Retorna True se uma derrota aconteceu."""
    killer = killer or g.players[0]
    for _ in range(max_frames):
        car = g.mode_runner.car
        if car.alive and car.stomp_lock <= 0:
            g.on_stomp(car, killer)
            if not car.alive:
                tick(g, 1)      # deixa o CrazyCarMode.update() do próximo quadro criar o carro do novo nível
                return True
        tick(g, 1)
    return False


def test_crazy_car_inicio_e_hud():
    g = mk(1, mode="crazy_car", seed=41)
    check(g.mode_runner is not None, "mode_runner deveria existir em crazy_car")
    check(g.mode_runner.mode_key == "crazy_car", "mode_key incorreto")
    check(g.wave.state == "mode", f"WaveManager deveria estar em 'mode', está em {g.wave.state!r}")
    check(g.mode_runner.level == 1, "deveria começar no nível 1")
    car = g.mode_runner.car
    check(car is not None and car.alive, "o carro deveria existir desde o início")
    check(car.impacts_left == S.CRAZY_CAR_IMPACTS_BY_LEVEL[0], f"nível 1 deveria ter {S.CRAZY_CAR_IMPACTS_BY_LEVEL[0]} impactos")
    check(car.phasing_enabled is True, "phasing deveria estar sempre ativo neste modo")
    check(car in g.wave.cars and car in g.wave.enemies and car in g.wave.solos,
          "o carro deveria estar nas listas normais do WaveManager (collisions.py depende delas)")
    lines = g.mode_runner.hud_lines()
    check(any("NÍVEL" in t for t, _ in lines), f"HUD sem NÍVEL: {lines}")
    check(any("CARRO" in t for t, _ in lines), f"HUD sem referência ao carro: {lines}")
    tick(g, 1, draw=True)


def test_crazy_car_spawna_sempre_na_borda_direita():
    """Teste 11 do design doc: nasce na borda direita, inclusive após reaparecer/avançar de nível."""
    g = mk(1, mode="crazy_car", seed=42)
    right_x = CyberCar.spawn_x()
    check(abs(g.mode_runner.car.x - right_x) < 1.0, f"carro deveria nascer em x={right_x}, nasceu em {g.mode_runner.car.x}")
    check(g.mode_runner.car.dir == -1, "carro nascido na direita deveria ir para a esquerda primeiro")
    for _ in range(3):
        ok = defeat_car(g)
        check(ok, "não conseguiu derrotar o carro dentro do limite de quadros do teste")
        check(abs(g.mode_runner.car.x - right_x) < 1.0,
              f"carro do próximo nível deveria nascer em x={right_x}, nasceu em {g.mode_runner.car.x}")

    # a mesma regra vale no Clássico e no 50 Rounds (seção 8.9) — checada aqui de novo por segurança,
    # já que CyberCar.spawn_x() é compartilhado entre os três modos.
    g2 = mk(2, mode="classic", seed=43)
    to_combat(g2, 7)
    car2 = g2.wave.cars[0] if g2.wave.cars else None
    check(car2 is not None, "round 7 do Clássico deveria ter um CyberCar")
    check(abs(car2.x - right_x) < 1.0, f"CyberCar do Clássico deveria nascer em x={right_x}, nasceu em {car2.x}")


def test_crazy_car_derrota_e_fica_mais_dificil():
    """Teste 5, 6 e 7 do design doc: carro derrotado -> nível sobe -> mais vida e mais velocidade."""
    g = mk(1, mode="crazy_car", seed=44)
    mr = g.mode_runner
    levels_seen = [(mr.level, mr.car.impacts_max, mr.car.speed)]
    for _ in range(4):
        ok = defeat_car(g)
        check(ok, "não conseguiu derrotar o carro")
        levels_seen.append((mr.level, mr.car.impacts_max, mr.car.speed))
    check([lv for lv, _, _ in levels_seen] == [1, 2, 3, 4, 5], f"níveis deveriam subir 1 a 1: {levels_seen}")
    for i in range(1, len(levels_seen)):
        _, impacts_prev, speed_prev = levels_seen[i - 1]
        _, impacts_now, speed_now = levels_seen[i]
        check(impacts_now >= impacts_prev, f"vida não deveria cair entre níveis: {levels_seen}")
        check(speed_now > speed_prev, f"velocidade deveria crescer a cada nível: {levels_seen}")
    check(mr.defeats == 4, f"deveria registrar 4 derrotas, registrou {mr.defeats}")
    check([imp for _, imp, _ in levels_seen[:6]] == list(S.CRAZY_CAR_IMPACTS_BY_LEVEL[:5]),
          f"tabela de impactos não bate com CRAZY_CAR_IMPACTS_BY_LEVEL: {levels_seen}")


def test_crazy_car_vida_e_velocidade_tem_teto():
    impacts_far = CrazyCarMode._impacts_for_level(500)
    speed_far = CrazyCarMode._speed_for_level(500)
    check(impacts_far <= S.CRAZY_CAR_MAX_IMPACTS, "impactos não deveriam ultrapassar o teto configurado")
    check(speed_far <= S.CRAZY_CAR_MAX_SPEED + 1e-9, "velocidade não deveria ultrapassar o teto configurado")


def test_crazy_car_turbo_progressivo():
    """Teste 8: sem turbo nos primeiros níveis, turbo cada vez mais frequente depois."""
    for lvl in range(1, S.CRAZY_CAR_TURBO_START_LEVEL):
        turbo, chance = CrazyCarMode._turbo_for_level(lvl)
        check(turbo is False, f"nível {lvl} não deveria ter turbo ainda")
    turbo, chance_start = CrazyCarMode._turbo_for_level(S.CRAZY_CAR_TURBO_START_LEVEL)
    check(turbo is True, f"nível {S.CRAZY_CAR_TURBO_START_LEVEL} deveria ativar o turbo")
    _, chance_later = CrazyCarMode._turbo_for_level(S.CRAZY_CAR_TURBO_START_LEVEL + 5)
    check(chance_later > chance_start, "a chance/frequência de turbo deveria crescer com o nível")
    check(chance_later <= S.CRAZY_CAR_TURBO_CHANCE_MAX + 1e-9, "chance de turbo não deveria ultrapassar o teto")


def test_crazy_car_foguetes_progressivos():
    """Teste 9: sem foguetes nos primeiros níveis, foguetes cada vez mais presentes depois."""
    for lvl in range(1, S.CRAZY_CAR_ROCKETS_START_LEVEL):
        check(CrazyCarMode._rockets_for_level(lvl) is None, f"nível {lvl} não deveria ter foguetes ainda")
    cfg_start = CrazyCarMode._rockets_for_level(S.CRAZY_CAR_ROCKETS_START_LEVEL)
    check(cfg_start is not None, "nível de início dos foguetes deveria liberar foguetes")
    cfg_later = CrazyCarMode._rockets_for_level(S.CRAZY_CAR_ROCKETS_START_LEVEL + 6)
    check(cfg_later["max_alive"] >= cfg_start["max_alive"], "quantidade máxima de foguetes deveria crescer com o nível")
    check(cfg_later["interval"][1] <= cfg_start["interval"][1], "frequência de foguetes deveria aumentar (intervalo menor)")
    check(cfg_later["max_alive"] <= S.CRAZY_CAR_ROCKETS_MAX_ALIVE_CAP, "quantidade de foguetes estourou o teto")

    # foguetes nascem de verdade quando o nível libera (física real, não só a config)
    g = mk(1, mode="crazy_car", seed=45)
    g.mode_runner.level = S.CRAZY_CAR_ROCKETS_START_LEVEL
    g.mode_runner._spawn_car()
    tick(g, 60 * 8)
    check(len(g.wave.hazards.rockets) > 0, "nenhum foguete nasceu de verdade em 8s no nível com foguetes liberados")


def test_crazy_car_phasing_completo():
    """Teste 10 do design doc, dentro do fluxo oficial do CrazyCarMode (não isolado como na fundação)."""
    g = mk(2, mode="crazy_car", seed=46)
    p0, p1 = g.players
    car = g.mode_runner.car
    car.speed = 0.0
    p0.x, p0.y, p0.vy, p0.on_ground, p0.invuln = car.x, car.hb[1] - 5, 300.0, False, 0.0
    tick(g, 1, shield=False)
    check(car.impacts_left == car.impacts_max - 1, "o pouso deveria contar como 1 impacto válido")
    check(p0.standing is None, "o jogador não deveria ficar apoiado sobre o carro (phasing)")
    check(car.is_phasing(p0) is True, "phasing deveria estar ativo para p0 logo após o impacto")
    check(car.is_phasing(p1) is False, "phasing não deveria afetar p1, que nunca tocou o carro")
    lives_before = p0.lives
    for _ in range(50):
        p0.vy = 50.0
        tick(g, 1, shield=False)
    check(p0.lives == lives_before, "não deveria haver dano de contato durante a janela de phasing")
    # expira o phasing e encosta na lateral: a colisão deve voltar ao normal, sem dano duplicado/abrupto
    tick(g, int(S.CRAZY_CAR_PLAYER_PHASING_DURATION * 60), shield=False)
    car = g.mode_runner.car     # pode ter sido substituído se foi derrotado nesse meio-tempo; não deveria aqui
    p0.x, p0.y = car.hb[0] - p0.HIT_W / 2 + 2, (car.hb[1] + car.hb[3]) / 2
    p0.vy, p0.on_ground = 0.0, True
    tick(g, 1, shield=False)
    check(p0.lives == lives_before - 1, f"deveria ter tomado exatamente 1 dano ao encostar após o phasing: {p0.lives}")


def test_crazy_car_gameover_e_recorde():
    g = mk(1, mode="crazy_car", seed=47)
    defeat_car(g)   # garante ao menos 1 derrota registrada antes do game over
    p = g.players[0]
    p.effects.pop("shield", None)
    p.lives = 0
    p.eliminated = True
    g.on_player_eliminated(p)
    tick(g, 1)
    check(g.state == "gameover", f"deveria ter terminado a partida, estado={g.state!r}")
    is_new, record = g.mode_record_result
    check(is_new is True, "primeiro resultado da sessão deveria virar recorde")
    check(record == g.mode_runner.level, "recorde deveria ser o nível do carro alcançado")
    check(g.config.get_record("crazy_car") == record, "recorde não refletido no ConfigManager")
    result = dict(g.mode_runner.result_lines())
    for key in ("NÍVEL DO CARRO", "CARROS DERROTADOS", "MELHOR NÍVEL"):
        check(key in result, f"result_lines sem {key}: {result}")
    tick(g, int(S.GAMEOVER_INPUT_LOCK * 60) + 5, draw=True)


def test_crazy_car_1_a_4_jogadores():
    """Teste 12 (parcial, para este modo): o Crazy Car deve funcionar igual com 1 a 4 jogadores."""
    for n in (1, 2, 3, 4):
        g = mk(n, mode="crazy_car", seed=48 + n)
        check(len(g.players) == n, f"deveria ter {n} jogadores")
        check(g.mode_runner.car is not None and g.mode_runner.car.alive, f"carro deveria existir com {n} jogadores")
        tick(g, 30, draw=True)
        check(g.wave.state == "mode", f"wave.state deveria continuar 'mode' com {n} jogadores")


def test_crazy_car_nao_quebra_outros_modos():
    g = mk(2, mode="classic", seed=52)
    check(g.mode_runner is None, "Clássico não deveria ter mode_runner")
    to_combat(g, 1)
    check(g.wave.state == "active" and len(g.wave.enemies) > 0, "round 1 do Clássico sem inimigos")

    g2 = mk(1, mode="mechanic_room", seed=53)
    tick(g2, 30)
    check(g2.mode_runner.wave_no == 1, "Mechanic Room deveria continuar funcionando normalmente")


TESTS = [v for k, v in sorted(globals().items(), key=lambda kv: kv[1].__code__.co_firstlineno if callable(kv[1]) and hasattr(kv[1], "__code__") else 0)
         if k.startswith("test_")]


def main(argv):
    wanted = [a.lower() for a in argv]
    ran = failed = 0
    for fn in TESTS:
        if wanted and not any(w in fn.__name__ for w in wanted):
            continue
        before = len(FAILS)
        print(f"- {fn.__name__}")
        t0 = time.time()
        try:
            fn()
        except Exception as exc:                # noqa: BLE001
            import traceback
            traceback.print_exc()
            FAILS.append(f"{fn.__name__}: EXCEÇÃO {exc!r}")
        ran += 1
        ok = len(FAILS) == before
        failed += (not ok)
        print(f"  {'OK' if ok else 'FALHOU'}  ({time.time() - t0:.1f}s)")
    print(f"\n{ran - failed}/{ran} testes passaram")
    if FAILS:
        print("\nFalhas:")
        for f in FAILS:
            print(" -", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
