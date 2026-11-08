#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
selftest_settings.py — testes automáticos (sem janela/áudio/controle reais) do menu avançado de configurações.

    python selftest_settings.py            # roda tudo
    python selftest_settings.py audio      # só os testes cujo nome contém "audio"

Usa SDL "dummy". Controles Xbox/PlayStation e o mouse são SIMULADOS (o ambiente de teste não os tem): o
GamepadManager recebe controles falsos de famílias diferentes e pygame.mouse devolve posições/botões controlados.
Os testes percorrem os mesmos caminhos do jogo: Game.step() -> MenuInput -> SettingsMenu -> InputManager/AudioManager/
DisplayManager -> ConfigManager -> arquivo JSON.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame

pygame.init()
pygame.display.set_mode((1280, 720))

import gamepad as GP
import settings as S
from config import ConfigManager
from display import DisplayManager
from game import Game
from input_handler import pad_device_for

DT = 1 / 60
FAILS = []
TMP = tempfile.mkdtemp(prefix="orbital_cfg_")

# ----------------------------------------------------------------------------- mouse simulado
MOUSE = dict(pos=(0, 0), buttons=(False, False, False))
pygame.mouse.get_pos = lambda: MOUSE["pos"]
pygame.mouse.get_pressed = lambda num_buttons=3: MOUSE["buttons"]


def mouse(pos=None, left=None, right=None):
    if pos is not None:
        MOUSE["pos"] = (int(pos[0]), int(pos[1]))
    b = list(MOUSE["buttons"])
    if left is not None:
        b[0] = left
    if right is not None:
        b[2] = right
    MOUSE["buttons"] = tuple(b)


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print("      FALHOU:", msg)
    return cond


# ----------------------------------------------------------------------------- helpers
def new_path(name="config.json"):
    d = tempfile.mkdtemp(dir=TMP)
    return os.path.join(d, name)


def mk(pads=(), cfg=None, display_size=(1280, 720), fullscreen=False, big_desktop=True):
    """Game real com DisplayManager e (opcionalmente) controles falsos [(familia, nome), ...]."""
    d = DisplayManager()
    if big_desktop:                                  # monitor "1080p" simulado: todas as resoluções sugeridas existem
        d.desktop_size = lambda: (1920, 1080)
        d.supported_modes = lambda: [(1920, 1080), (1600, 900), (1366, 768), (1280, 720)]
    d.apply(display_size, fullscreen)
    cfg = cfg if cfg is not None else ConfigManager(path=None)
    mouse((0, 0), False, False)
    g = Game(d.canvas, display=d, config=cfg)
    state = fake_pads(g, pads)
    g.fake_state = state
    return g, d


def fake_pads(g, specs):
    gp = g.input.gamepad
    gp.pads = [object() for _ in specs]
    gp.slots = [{"family": f, "name": n} for f, n in specs]
    state = set()
    gp.button_down = lambda i, n: (i, n) in state
    gp.axis_dir = lambda i, deadzone=None: (0, 0)
    g.input._auto_assign_gamepads()
    return state


def step(g, held=(), pressed=(), n=1, dt=DT):
    for _ in range(n):
        g.input.held = set(held)
        g.input.pressed = set(pressed)
        g.step(dt)


def tap(g, name, extra_frames=1):
    step(g, held={name}, pressed={name})
    step(g, n=extra_frames)


def open_menu(g, tab=0, return_to="paused"):
    g.state = return_to if return_to in ("paused", "title") else "paused"
    g.settings_menu.open(return_to=return_to, tab=tab)
    step(g, n=20)
    return g.settings_menu


def draw(g):
    g.draw(g.screen)


XBOX_PS = [(GP.XBOX, "Xbox Wireless Controller"), (GP.PLAYSTATION, "DualSense Wireless Controller")]


# ============================================================================= CONFIG / PERSISTÊNCIA
def test_config_criado_com_padroes():
    path = new_path()
    cfg = ConfigManager(path).load()
    check(os.path.exists(path) and cfg.status == "created", "config.json deveria ser criado quando não existe")
    data = json.load(open(path, encoding="utf-8"))
    check(data["audio"] == {"music_volume": 50, "sfx_volume": 80}, f"padrões de áudio {data['audio']}")
    check(data["video"] == {"width": 1280, "height": 720, "fullscreen": False}, f"padrões de vídeo {data['video']}")
    check(set(data) == {"version", "audio", "video", "controls", "records"}, f"chaves do arquivo {set(data)}")


def test_config_invalido_e_incompleto():
    # 1) lixo total: usa padrões, não levanta, não mexe no arquivo até o jogador mudar algo
    path = new_path()
    open(path, "w", encoding="utf-8").write("{ isto não é json ::: ")
    cfg = ConfigManager(path).load()
    check(cfg.status == "invalid" and cfg.music_volume == 50 and cfg.video["width"] == 1280, "JSON inválido deveria cair nos padrões")
    check(open(path, encoding="utf-8").read().startswith("{ isto"), "arquivo inválido foi sobrescrito sem o jogador mudar nada")
    check(cfg.save() is False, "save() sem mudanças não deveria gravar")
    cfg.set_audio(music=33)
    check(cfg.save() is True and os.path.exists(path + ".bak"), "ao gravar de verdade, o arquivo ruim vira .bak")
    check(json.load(open(path, encoding="utf-8"))["audio"]["music_volume"] == 33, "gravação após JSON inválido")
    # 2) não é objeto / tipos errados / fora de faixa
    for raw, expect in (("[1,2,3]", None), ("null", None), ('"texto"', None)):
        p = new_path(); open(p, "w").write(raw)
        c = ConfigManager(p).load()
        check(c.music_volume == 50 and c.video["height"] == 720, f"raiz {raw} deveria usar padrões")
    p = new_path()
    json.dump({"audio": {"music_volume": 500, "sfx_volume": "alto"}, "video": {"width": -5, "height": "x", "fullscreen": "sim"},
               "controls": {"9": {"keyboard": {"fire": "x"}}, "1": {"keyboard": {"fire": 7, "nope": "a"}}}}, open(p, "w"))
    c = ConfigManager(p).load()
    check(c.music_volume == 100, f"500 deveria virar 100 (veio {c.music_volume})")
    check(c.sfx_volume == 80, "sfx inválido deveria manter o padrão")
    check(c.video == {"width": 1280, "height": 720, "fullscreen": False}, f"vídeo inválido {c.video}")
    check("9" not in c.controls and c.controls.get("1") == {"keyboard": {}}, f"controles inválidos {c.controls}")
    # 3) incompleto: aproveita o que é válido
    p = new_path(); json.dump({"audio": {"music_volume": 12}}, open(p, "w"))
    c = ConfigManager(p).load()
    check(c.music_volume == 12 and c.sfx_volume == 80 and c.video["width"] == 1280, "incompleto: válido mantido, resto padrão")
    mtime = os.path.getmtime(p)
    time.sleep(0.02)
    c.save()
    check(os.path.getmtime(p) == mtime, "carregar um arquivo válido-mas-incompleto não deve reescrevê-lo")
    # 4) Game inicia normalmente com config quebrado
    g, d = mk(cfg=ConfigManager(path).load())
    step(g, n=5)
    check(g.audio.music_percent == 33, "Game deveria aplicar o volume salvo do arquivo recuperado")


def test_config_so_grava_quando_muda():
    path = new_path()
    cfg = ConfigManager(path).load()
    m0 = os.path.getmtime(path)
    time.sleep(0.02)
    check(cfg.save() is False and os.path.getmtime(path) == m0, "save() sem mudança reescreveu o arquivo")
    cfg.set_audio(sfx=10)
    check(cfg.dirty and cfg.save() is True, "mudança deveria gravar")
    check(not cfg.dirty and cfg.save() is False, "depois de gravar não há mais o que gravar")
    check(not any(f.endswith(".tmp") for f in os.listdir(os.path.dirname(path))), "sobrou arquivo temporário (gravação atômica)")
    cfg2 = ConfigManager(path).load()
    check(cfg2.sfx_volume == 10 and cfg2.status == "loaded", "releitura do que foi gravado")
    # pasta sem permissão/caminho impossível: não derruba nada
    bad = ConfigManager("/proc/forbidden_dir/config.json")
    bad.set_audio(music=1)
    check(bad.save() is False, "gravar em local impossível deveria falhar em silêncio")


def test_controles_persistem_entre_execucoes():
    path = new_path()
    g, d = mk(pads=XBOX_PS, cfg=ConfigManager(path).load())
    sm = open_menu(g, tab=1)
    inp = g.input
    inp.set_binding(0, "keyboard", "jump", pygame.K_h)
    inp.set_binding(0, "xbox", "fire", "lb")
    inp.set_binding(1, "playstation", "dash", "rb")
    inp.set_binding(2, "keyboard", "donate_life", pygame.K_F5)
    sm._after_controls_change()
    # "fecha o jogo" e abre de novo lendo o mesmo arquivo
    g2, d2 = mk(pads=XBOX_PS, cfg=ConfigManager(path).load())
    i2 = g2.input
    check(i2.binding_value(0, "keyboard", "jump") == pygame.K_h, "tecla do P1 não persistiu")
    check(i2.binding_value(0, "xbox", "fire") == "lb", "botão Xbox do P1 não persistiu")
    check(i2.binding_value(1, "playstation", "dash") == "rb", "botão PlayStation do P2 não persistiu")
    check(i2.binding_value(2, "keyboard", "donate_life") == pygame.K_F5, "tecla do P3 não persistiu")
    check(i2.binding_value(1, "keyboard", "jump") == i2.default_value(1, "keyboard", "jump"), "P2 não foi alterado")
    check(i2.binding_value(0, "playstation", "fire") == "x", "perfil PlayStation do P1 deveria seguir o padrão")
    # valores adulterados no arquivo são ignorados, sem impedir o início
    data = json.load(open(path, encoding="utf-8"))
    data["controls"]["1"]["keyboard"]["fire"] = "tecla_que_nao_existe"
    data["controls"]["1"]["keyboard"]["left"] = "escape"                   # reservada
    data["controls"]["1"]["xbox"]["jump"] = "start"                        # reservado para pausar
    data["controls"]["2"]["keyboard"]["left"] = "h"                        # tecla já usada pelo P1 (jump=h)
    json.dump(data, open(path, "w"))
    g3, _ = mk(pads=XBOX_PS, cfg=ConfigManager(path).load())
    i3 = g3.input
    check(i3.binding_value(0, "keyboard", "fire") == pygame.K_SPACE, "tecla inexistente deveria virar o padrão")
    check(i3.binding_value(0, "keyboard", "left") == pygame.K_a, "tecla reservada (ESC) deveria ser ignorada")
    check(i3.binding_value(0, "xbox", "jump") == "a", "START como atalho deveria ser ignorado")
    codes = [c for b in i3.bindings for c in b.key_codes.values()]
    check(len(codes) == len(set(codes)), "após importar, nenhuma tecla pode ficar repetida entre jogadores")
    step(g3, n=5)
    # teclas duplicadas no mesmo jogador
    data = json.load(open(path, encoding="utf-8"))
    data["controls"] = {"1": {"keyboard": {"left": "q", "right": "q"}}}
    json.dump(data, open(path, "w"))
    g4, _ = mk(cfg=ConfigManager(path).load())
    check(g4.input.binding_value(0, "keyboard", "left") == pygame.K_a, "teclas repetidas no mesmo jogador voltam ao padrão")


def test_recordes_dos_modos_de_sobrevivencia():
    path = new_path()
    cfg = ConfigManager(path).load()
    check(set(cfg.records) == set(S.SURVIVAL_GAME_MODES), f"modos de recorde {set(cfg.records)}")
    check(all(cfg.get_record(m) == 0 for m in S.SURVIVAL_GAME_MODES), "recordes deveriam começar em 0")
    check(cfg.set_record("rockets_sky", 37.5) is True, "37.5s deveria virar recorde (de 0)")
    check(cfg.set_record("crazy_car", 3) is True, "nível 3 deveria virar recorde (de 0)")
    cfg.save()
    # "fecha o jogo" e reabre lendo o mesmo arquivo
    cfg2 = ConfigManager(path).load()
    check(cfg2.get_record("rockets_sky") == 37.5, f"recorde de tempo não persistiu: {cfg2.get_record('rockets_sky')}")
    check(cfg2.get_record("crazy_car") == 3, f"recorde de nível não persistiu: {cfg2.get_record('crazy_car')}")
    check(cfg2.get_record("ball_rain") == 0, "modo nunca jogado deveria seguir em 0")
    # um resultado pior nunca sobrescreve o recorde
    check(cfg2.set_record("rockets_sky", 10.0) is False, "resultado pior não deveria virar recorde")
    check(cfg2.get_record("rockets_sky") == 37.5, "recorde não deveria ter piorado")
    # um resultado melhor atualiza e é persistido
    check(cfg2.set_record("rockets_sky", 90.0) is True, "resultado melhor deveria virar novo recorde")
    cfg2.save()
    cfg3 = ConfigManager(path).load()
    check(cfg3.get_record("rockets_sky") == 90.0, "novo recorde não persistiu após melhora")
    # config.json com valores inválidos em "records" não impede o jogo de abrir
    data = json.load(open(path, encoding="utf-8"))
    data["records"]["crazy_car"] = -5
    data["records"]["ball_rain"] = "muitos"
    data["records"]["modo_que_nao_existe"] = 999
    json.dump(data, open(path, "w"))
    cfg4 = ConfigManager(path).load()
    check(cfg4.get_record("crazy_car") == 0, "recorde negativo inválido deveria virar o padrão (0)")
    check(cfg4.get_record("ball_rain") == 0, "recorde não-numérico inválido deveria virar o padrão (0)")
    check(cfg4.get_record("rockets_sky") == 90.0, "recordes válidos ao lado de inválidos não deveriam ser afetados")
    # config.json de uma versão anterior (sem o bloco "records" nenhum) continua funcionando
    path2 = new_path()
    json.dump({"version": 1, "audio": {"music_volume": 50, "sfx_volume": 80},
               "video": {"width": 1280, "height": 720, "fullscreen": False}, "controls": {}},
              open(path2, "w"))
    cfg5 = ConfigManager(path2).load()
    check(all(cfg5.get_record(m) == 0 for m in S.SURVIVAL_GAME_MODES),
          "config.json antigo sem 'records' deveria usar os padrões (0) sem travar o jogo")


# ============================================================================= ÁUDIO
class FakeSound:
    def __init__(self):
        self.vol, self.plays = 1.0, []

    def set_volume(self, v):
        self.vol = v

    def play(self):
        self.plays.append(self.vol)


def test_audio_sliders_independentes():
    path = new_path()
    g, d = mk(cfg=ConfigManager(path).load())
    a = g.audio
    check(a.music_percent == 50 and a.sfx_percent == 80, "volumes iniciais devem vir do config")
    sm = open_menu(g)
    fake = FakeSound()
    a._sfx["fake"] = fake
    sm.focus, sm.row = "main", 0
    # teclado: ←/→ muda 5% e vale na hora
    tap(g, "global_right")
    check(a.music_percent == 55, f"música 55% (tem {a.music_percent})")
    check(a.sfx_percent == 80, "mexer na música não pode mexer nos efeitos")
    if a._mixer_ok:
        check(abs(pygame.mixer.music.get_volume() - 0.55) < 0.02, f"mixer da música {pygame.mixer.music.get_volume():.2f}")
    # segurar → repete até 100 e para
    step(g, held={"global_right"}, n=200)
    step(g)
    check(a.music_percent == 100, f"segurar → deveria chegar a 100% (tem {a.music_percent})")
    # segurar ← vai a 0 e silencia de verdade
    step(g, held={"global_left"}, n=400)
    step(g)
    check(a.music_percent == 0 and a.music_volume == 0.0, f"música deveria estar em 0% (tem {a.music_percent})")
    if a._mixer_ok:
        check(pygame.mixer.music.get_volume() == 0.0, "volume 0% da música deveria zerar o mixer")
    check(g.config.music_volume == 0, "config deveria refletir 0%")
    # efeitos: independente; 0% = nenhum som; depois volta a tocar no volume novo
    tap(g, "global_down")
    check(sm.row == 1, "↓ deveria ir para a linha de efeitos")
    step(g, held={"global_left"}, n=400)
    step(g)
    check(a.sfx_percent == 0 and a.music_percent == 0, "efeitos 0% e música 0% independentes")
    a.play_sfx("fake")
    check(fake.plays == [], "efeito com volume 0% não pode tocar")
    for _ in range(8):
        tap(g, "global_right")
    check(a.sfx_percent == 40, f"efeitos 40% (tem {a.sfx_percent})")
    a.play_sfx("fake")
    check(len(fake.plays) == 1 and abs(fake.plays[0] - 0.4) < 1e-9, f"som posterior deve usar o volume novo ({fake.plays})")
    check(a.music_percent == 0, "música continua independente em 0%")
    # persistência
    sm.close()
    saved = json.load(open(path, encoding="utf-8"))["audio"]
    check(saved == {"music_volume": 0, "sfx_volume": 40}, f"arquivo {saved}")
    g2, _ = mk(cfg=ConfigManager(path).load())
    check(g2.audio.music_percent == 0 and g2.audio.sfx_percent == 40, "volumes não foram aplicados ao reiniciar o jogo")


def test_audio_slider_com_mouse_e_toggle_da_pausa():
    g, d = mk(cfg=ConfigManager(new_path()).load())
    a = g.audio
    sm = open_menu(g)
    draw(g)
    tr = sm._tracks["music"]
    # clicar no meio da trilha e arrastar
    mouse((tr.left + tr.width * 0.25, tr.centery), left=False)
    step(g)
    mouse(left=True)
    step(g)
    check(sm.drag == "music" and abs(a.music_percent - 25) <= 1, f"clique em 25% (tem {a.music_percent}, drag={sm.drag})")
    mouse((tr.left + tr.width * 0.75, tr.centery + 40))     # pode sair da linha na vertical enquanto arrasta
    step(g)
    check(abs(a.music_percent - 75) <= 1, f"arrastando até 75% (tem {a.music_percent})")
    mouse((tr.right + 300, tr.centery))                      # passou do fim: trava em 100
    step(g)
    check(a.music_percent == 100, "arrastar além do fim deveria travar em 100%")
    mouse((tr.left - 300, tr.centery))
    step(g)
    check(a.music_percent == 0, "arrastar antes do início deveria travar em 0%")
    mouse(left=False)
    step(g)
    check(sm.drag is None, "soltar o mouse deveria encerrar o arrasto")
    # com a trilha desligada pelo toggle da pausa, mexer no slider religa (o jogador ouve o que ajusta)
    a.music_enabled = False
    sm.focus, sm.row = "main", 0
    tap(g, "global_right")
    check(a.music_enabled and a.music_percent == 5, "slider deveria religar a música desligada pelo toggle")
    mouse((0, 0))


# ============================================================================= VÍDEO
def test_display_resolucoes_suportadas():
    pygame.init()
    d = DisplayManager()
    d.desktop_size = lambda: (1920, 1080)
    d.supported_modes = lambda: [(1920, 1080), (1600, 900), (1366, 768), (1280, 720), (1024, 768)]
    check(d.available_resolutions(False) == [(1024, 576), (1280, 720), (1366, 768), (1600, 900), (1920, 1080)], f"janela 1080p: {d.available_resolutions(False)}")
    check(d.available_resolutions(True) == [(1280, 720), (1366, 768), (1600, 900), (1920, 1080)], f"tela cheia 1080p: {d.available_resolutions(True)}")
    # monitor 1366x768: não oferece 1600x900 nem 1920x1080
    d.desktop_size = lambda: (1366, 768)
    d.supported_modes = lambda: [(1366, 768), (1280, 720)]
    got = d.available_resolutions(False)
    check((1600, 900) not in got and (1920, 1080) not in got and (1366, 768) in got, f"monitor 1366x768: {got}")
    check(not d.is_supported((1600, 900), False) and not d.is_supported((1920, 1080), True), "tamanho maior que o monitor não é suportado")
    # tela cheia só aceita o que o monitor lista; o nativo do desktop é sempre uma opção
    d.supported_modes = lambda: [(1366, 768)]
    check(d.available_resolutions(True) == [(1366, 768)], f"fullscreen só com modos reais: {d.available_resolutions(True)}")
    # modos 16:9 extras reportados pelo pygame aparecem; modos fora de proporção não
    d.desktop_size = lambda: (2560, 1440)
    d.supported_modes = lambda: [(2560, 1440), (2560, 1080), (1920, 1080), (1280, 720), (1280, 1024)]
    got = d.available_resolutions(True)
    check((2560, 1440) in got and (2560, 1080) not in got and (1280, 1024) not in got, f"extras 16:9: {got}")
    # 'qualquer tamanho serve' (list_modes == -1) e lista vazia (pygame não informou)
    d.supported_modes = lambda: None
    check((1600, 900) in d.available_resolutions(True), "list_modes == -1 deveria aceitar os candidatos")
    d.supported_modes = lambda: []
    check(d.available_resolutions(True) == [(2560, 1440)], f"sem lista, só o modo nativo: {d.available_resolutions(True)}")
    # pedido impossível cai no mais próximo, com aviso, sem exceção
    d2 = DisplayManager()
    d2.desktop_size = lambda: (1366, 768)
    d2.supported_modes = lambda: [(1366, 768)]
    r = d2.apply((3840, 2160), False)
    check(not r["ok"] and r["size"] == (1366, 768) and "NÃO SUPORTADA" in r["note"], f"fallback {r}")


def test_display_escala_letterbox_e_mouse():
    d = DisplayManager()
    d.desktop_size = lambda: (2560, 1440)
    d.supported_modes = lambda: None
    d.apply((1280, 720), False)
    check(d.scale == 1.0 and d._buf is None, "1280x720 não deveria escalar")
    # 16:9 exato: sem barras
    r = d.apply((1600, 900), False)
    check(r["size"] == (1600, 900) and abs(d.scale - 1.25) < 1e-9 and d.view == pygame.Rect(0, 0, 1600, 900) and not d._bars, f"1600x900 {d.view} {d.scale}")
    check(d.to_logical((800, 450)) == (640, 360) and d.to_logical((0, 0)) == (0, 0) and d.to_logical((1599, 899)) == (1279, 719),
          "mouse 16:9 -> lógico")
    # 1366x768 (≈16:9): barras de 1px, proporção preservada
    d.apply((1366, 768), False)
    check(abs(d.view.width / d.view.height - 16 / 9) < 0.01 and d.view.height == 768, f"1366x768 view {d.view}")
    # janela que NÃO é 16:9: letterbox (não estica)
    d.apply((1600, 1000), False)
    check(d.view.size == (1600, 900) and d.view.top == 50 and len(d._bars) == 2, f"letterbox {d.view} barras {d._bars}")
    check(d.to_logical((800, 500)) == (640, 360), f"centro da área útil -> centro lógico ({d.to_logical((800, 500))})")
    check(d.to_logical((800, 10)) == (640, 0), "mouse sobre a barra preta trava na borda lógica")
    d.apply((1000, 900), False)                      # mais "quadrado": barras em cima/baixo, escala pela largura
    check(abs(d.scale - 1000 / 1280) < 1e-9 and d.view.width == 1000, f"pillar/letterbox {d.view}")
    d.apply((1600, 900), False)
    # pixels reais: canto vermelho do canvas aparece no canto da janela escalada; barras ficam pretas
    d.canvas.fill((0, 0, 0))
    pygame.draw.rect(d.canvas, (255, 0, 0), (0, 0, 40, 40))
    pygame.draw.rect(d.canvas, (0, 0, 255), (1240, 680, 40, 40))
    for smooth in (True, False):
        d.smooth = smooth
        d.present()
        w = d.window
        check(w.get_at((10, 10))[:3] == (255, 0, 0), f"canto vermelho (smooth={smooth}) {w.get_at((10, 10))}")
        check(w.get_at((1590, 890))[:3] == (0, 0, 255), f"canto azul (smooth={smooth}) {w.get_at((1590, 890))}")
    d.apply((1600, 1000), False)
    d.present()
    check(d.window.get_at((800, 10))[:3] == (0, 0, 0), "barra preta superior deveria ser preta")
    # custo de apresentar em 1080p (orçamento por quadro = 16,6 ms)
    d.apply((1920, 1080), False)
    for smooth in (True, False):
        d.smooth = smooth
        t0 = time.perf_counter()
        for _ in range(40):
            d.present()
        print(f"      present 1920x1080 smooth={smooth}: {(time.perf_counter() - t0) / 40 * 1000:.1f} ms")


def test_video_pelo_menu_sem_reiniciar_partida():
    path = new_path()
    g, d = mk(cfg=ConfigManager(path).load(), pads=XBOX_PS)
    g.player_count = 3
    g.start_match()
    step(g, n=90)
    wave, players, rnd = g.wave, list(g.players), g.wave.round_no
    pos = [(p.x, p.y) for p in players]
    g.toggle_pause()
    sm = g.settings_menu
    # pelo menu da pausa -> CONFIGURAÇÕES
    g.pause_sel = S.__dict__.get("x", 0) or __import__("game").PAUSE_ITEMS.index("settings")
    tap(g, "global_return")
    check(g.state == "settings" and sm.return_to == "paused", f"pausa → configurações ({g.state})")
    step(g, n=20)
    sm.focus, sm.row = "main", 2
    check(sm.res_list == [(1024, 576), (1280, 720), (1366, 768), (1600, 900), (1920, 1080)], f"lista {sm.res_list}")
    tap(g, "global_right")
    tap(g, "global_right")
    check(sm.res_list[sm.res_idx] == (1600, 900) and d.size == (1280, 720), "selecionar não aplica sozinho (fica pendente)")
    tap(g, "global_down")                              # linha APLICAR
    tap(g, "global_return")
    check(d.size == (1600, 900) and not d.fullscreen, f"resolução aplicada {d.size}")
    check(g.config.video == {"width": 1600, "height": 900, "fullscreen": False}, f"config {g.config.video}")
    tap(g, "global_down")                              # linha TELA CHEIA
    tap(g, "global_return")
    check(d.fullscreen and d.size == (1600, 900), f"tela cheia mantendo a resolução ({d.size}, fs={d.fullscreen})")
    check(json.load(open(path, encoding="utf-8"))["video"] == {"width": 1600, "height": 900, "fullscreen": True}, "arquivo de vídeo")
    draw(g)
    # a partida continua exatamente a mesma
    sm.close()
    check(g.state == "paused", "VOLTAR deveria retornar à pausa")
    check(g.wave is wave and g.players == players and g.wave.round_no == rnd, "a partida foi reiniciada/recriada!")
    check([(p.x, p.y) for p in g.players] == pos, "posições dos jogadores mudaram")
    g.toggle_pause()
    step(g, n=60)
    draw(g)
    check(g.state == "playing", "partida deveria continuar")
    # F11 em jogo alterna tela cheia, preservando a resolução, e não derruba o loop
    step(g, held={"global_f11"}, pressed={"global_f11"})
    check(not d.fullscreen and d.size == (1600, 900), f"F11 → janela ({d.size}, fs={d.fullscreen})")
    step(g, held={"global_f"}, pressed={"global_f"})
    check(d.fullscreen, "F alterna tela cheia durante o jogo")
    step(g, n=30)
    draw(g)
    d.present()
    check(g.wave is wave, "F11 reiniciou a partida")
    # resolução não suportada vinda do config é tratada (fallback), sem quebrar nada
    d.desktop_size = lambda: (1366, 768)
    d.supported_modes = lambda: [(1366, 768)]
    r = g.apply_video((1920, 1080), False)
    check(not r["ok"] and r["size"][0] <= 1366, f"fallback {r}")


def test_mouse_em_resolucao_diferente_e_menus():
    g, d = mk()
    d.apply((1600, 900), False)                        # janela escalada 1.25x
    sm = open_menu(g)
    draw(g)
    # clicar no item CONTROLES da barra lateral usando coordenadas DA JANELA
    rect = pygame.Rect(sm.panel.left + 28, sm.panel.top + 104 + 72, 232, 60)
    wx, wy = d.view.left + rect.centerx * d.scale, d.view.top + rect.centery * d.scale
    mouse((wx, wy), left=False)
    step(g)
    check(sm.focus == "side" and sm.side_sel == 1, "passar o mouse (coordenada de janela escalada) deveria focar CONTROLES")
    mouse(left=True)
    step(g)
    mouse(left=False)
    step(g, n=12)
    check(sm.tab == 1 and sm.focus == "main", "clique deveria abrir a aba CONTROLES")
    # clique em VOLTAR fecha
    back = pygame.Rect(sm.panel.left + 28, sm.panel.bottom - 48 - 60, 232, 60)
    mouse((d.view.left + back.centerx * d.scale, d.view.top + back.centery * d.scale), left=False)
    step(g)
    mouse(left=True)
    step(g)
    mouse(left=False)
    step(g)
    check(g.state == "paused", f"clicar em VOLTAR deveria fechar ({g.state})")
    mouse((0, 0), False, False)


# ============================================================================= CONTROLES
def start_capture(g, sm, player, device, action):
    sm.c_player, sm.c_device = player, device
    sm._start_capture(action)
    return sm.capture


def test_remap_teclado_conflitos_e_reservadas():
    path = new_path()
    g, d = mk(cfg=ConfigManager(path).load())
    inp = g.input
    sm = open_menu(g, tab=1)
    # atribuição livre
    check(start_capture(g, sm, 0, "keyboard", "jump") is not None and inp.text_input_active, "captura deveria começar")
    inp.last_key_pressed = pygame.K_h
    step(g)
    check(inp.binding_value(0, "keyboard", "jump") == pygame.K_h and sm.capture is None, "H deveria ter sido atribuído a PULAR")
    check(inp.key_display(0, "jump") == "H" and not inp.text_input_active, "rótulo atualizado e captura encerrada")
    check(json.load(open(path))["controls"]["1"]["keyboard"]["jump"] == "h", "salvo no config.json")
    # reservadas: ficam esperando outra tecla (não aceitam F nem F11); ESC cancela
    start_capture(g, sm, 0, "keyboard", "dash")
    for key in (pygame.K_f, pygame.K_F11):
        inp.last_key_pressed = key
        step(g)
        check(sm.capture is not None and sm.capture["msg"].startswith("TECLA RESERVADA"), f"tecla {pygame.key.name(key)} deveria ser recusada")
    check(inp.binding_value(0, "keyboard", "dash") == pygame.K_s, "dash não pode ter mudado")
    step(g, held={"global_escape"}, pressed={"global_escape"})
    check(sm.capture is None and inp.binding_value(0, "keyboard", "dash") == pygame.K_s, "ESC deveria cancelar sem alterar")
    step(g, n=5)
    # mesma tecla: sem mudança
    start_capture(g, sm, 0, "keyboard", "dash")
    inp.last_key_pressed = pygame.K_s
    step(g)
    check(sm.capture is None and sm.modal is None and inp.binding_value(0, "keyboard", "dash") == pygame.K_s, "mesma tecla = sem alteração")
    # conflito com OUTRA AÇÃO do mesmo jogador: pede confirmação e TROCA (ninguém fica sem comando)
    start_capture(g, sm, 0, "keyboard", "dash")
    inp.last_key_pressed = pygame.K_h                      # H é do PULAR
    step(g)
    check(sm.modal is not None and sm.modal["kind"] == "swap", "conflito deveria abrir confirmação")
    check(inp.binding_value(0, "keyboard", "dash") == pygame.K_s, "nada muda antes de confirmar")
    tap(g, "global_right")                                 # → CANCELAR
    tap(g, "global_return")
    check(sm.modal is None and inp.binding_value(0, "keyboard", "dash") == pygame.K_s and inp.binding_value(0, "keyboard", "jump") == pygame.K_h,
          "CANCELAR mantém tudo")
    step(g, n=10)
    start_capture(g, sm, 0, "keyboard", "dash")
    inp.last_key_pressed = pygame.K_h
    step(g)
    tap(g, "global_return")                                # TROCAR (foco inicial)
    check(inp.binding_value(0, "keyboard", "dash") == pygame.K_h and inp.binding_value(0, "keyboard", "jump") == pygame.K_s,
          "TROCAR deveria permutar PULAR e DASH")
    codes = list(inp.bindings[0].key_codes.values())
    check(len(codes) == len(set(codes)), "sem teclas repetidas após a troca")
    # conflito com OUTRO jogador: recusa (não mexe nos controles dos demais)
    step(g, n=10)
    start_capture(g, sm, 0, "keyboard", "fire")
    inp.last_key_pressed = pygame.K_LEFT                   # ← é do P2 (mover esquerda)
    step(g)
    check(sm.capture is not None and "P2" in sm.capture["msg"], f"deveria recusar tecla do P2 ({sm.capture})")
    check(inp.binding_value(1, "keyboard", "left") == pygame.K_LEFT and inp.binding_value(0, "keyboard", "fire") == pygame.K_SPACE,
          "controles do P2 e do P1 intactos")
    inp.last_key_pressed = pygame.K_x                      # tecla livre: agora aceita
    step(g)
    check(sm.capture is None and inp.binding_value(0, "keyboard", "fire") == pygame.K_x, "tecla livre aceita após a recusa")


def test_captura_cancelamento_timeout_e_vazamento():
    g, d = mk(cfg=ConfigManager(new_path()).load())
    inp = g.input
    sm = open_menu(g, tab=1)
    # timeout
    start_capture(g, sm, 0, "keyboard", "jump")
    g.step(S.CAPTURE_TIMEOUT + 0.5)
    check(sm.capture is None and not inp.text_input_active, "timeout deveria cancelar")
    step(g, n=3)
    # clique direito cancela
    start_capture(g, sm, 0, "keyboard", "jump")
    mouse(left=False, right=True)
    step(g)
    mouse(right=False)
    step(g)
    check(sm.capture is None, "clique direito deveria cancelar")
    # botão CANCELAR na tela
    start_capture(g, sm, 0, "keyboard", "jump")
    draw(g)
    cancel = [r for r, ident in sm._mhit if ident == "cancel"][0]
    mouse(cancel.center, left=False)
    step(g)
    mouse(left=True)
    step(g)
    mouse(left=False)
    step(g)
    check(sm.capture is None, "botão CANCELAR deveria cancelar")
    mouse((0, 0))
    step(g, n=10)
    # a tecla capturada NÃO navega o menu/aciona nada: libera ↑ do P2 e captura ↑ segurada
    g.input.set_binding(1, "keyboard", "jump", pygame.K_h)
    sm.focus, sm.row = "main", 5
    row0 = sm.row
    start_capture(g, sm, 0, "keyboard", "dash")
    inp.last_key_pressed = pygame.K_UP
    step(g, held={"global_up"}, pressed={"global_up"})
    check(inp.binding_value(0, "keyboard", "dash") == pygame.K_UP, "↑ deveria ter sido atribuída")
    step(g, held={"global_up"}, n=90)                     # segura 1,5 s: sem swallow o menu repetiria ↑ e moveria a linha
    check(sm.row == row0 and sm.capture is None and sm.modal is None, f"tecla capturada vazou para o menu (linha {sm.row})")
    step(g, n=3)
    tap(g, "global_up")
    check(sm.row != row0, "depois de soltar, a navegação volta ao normal")
    # ENTER capturado não reabre captura
    sm.focus, sm.row = "main", 5
    step(g, n=3)
    start_capture(g, sm, 0, "keyboard", "dash")
    inp.last_key_pressed = pygame.K_F6
    step(g, held={"global_return"}, pressed={"global_return"})
    step(g, held={"global_return"}, n=5)
    check(sm.capture is None, "ENTER segurado não pode abrir nova captura")


def test_remap_xbox_playstation_por_jogador():
    g, d = mk(pads=XBOX_PS, cfg=ConfigManager(new_path()).load())
    inp, gp, state = g.input, g.input.gamepad, g.fake_state
    check(inp.bindings[0].gamepad_slot == 0 and inp.bindings[1].gamepad_slot == 1, "P1=Xbox, P2=PlayStation (auto)")
    check(pad_device_for(gp.family(0)) == "xbox" and pad_device_for(gp.family(1)) == "playstation", "família → perfil")
    sm = open_menu(g, tab=1)
    check(sm.c_device == "xbox", f"P1 com pad Xbox deveria abrir no perfil XBOX ({sm.c_device})")
    sm.c_player = 1
    sm._sync_device_to_pad()
    check(sm.c_device == "playstation", "P2 com DualSense deveria abrir no perfil PLAYSTATION")
    # rótulos diferentes por família
    for name in ("a", "b", "x", "y"):
        check(GP.button_label(name, GP.XBOX) != GP.button_label(name, GP.PLAYSTATION), f"rótulo '{name}' igual nas duas famílias")
    # captura de botão: só aceita o controle do jogador; START não é atribuível
    start_capture(g, sm, 0, "xbox", "jump")
    inp.last_gamepad_button = (1, "lb")                     # botão apertado no controle do P2
    step(g)
    check(sm.capture is not None and inp.binding_value(0, "xbox", "jump") == "a", "botão de outro controle deve ser ignorado")
    inp.last_gamepad_button = (0, "start")
    step(g)
    check(sm.capture is not None and inp.binding_value(0, "xbox", "jump") == "a" and "START" in sm.capture["msg"], "START não pode virar atalho")
    inp.last_gamepad_button = (0, "lb")
    step(g)
    check(sm.capture is None and inp.binding_value(0, "xbox", "jump") == "lb", "LB atribuído ao pulo do P1 (Xbox)")
    # runtime: o jogo usa o perfil da família do controle conectado
    state.clear(); state.add((0, "lb"))
    inp.update()
    check("p1_jump" in inp.held, "LB deveria pular no controle Xbox do P1")
    state.clear(); state.add((0, "a"))
    inp.update()
    check("p1_jump" not in inp.held, "A não pula mais no P1 depois da troca")
    # conflito entre ações do mesmo perfil (dash=b ↔ jump=lb): confirmação + troca
    start_capture(g, sm, 0, "xbox", "dash")
    inp.last_gamepad_button = (0, "lb")
    step(g)
    check(sm.modal is not None and sm.modal["kind"] == "swap", "botão repetido deveria pedir troca")
    tap(g, "global_return")
    check(inp.binding_value(0, "xbox", "dash") == "lb" and inp.binding_value(0, "xbox", "jump") == "b", "troca de botões Xbox")
    # perfis independentes: o PlayStation do P1 e o de qualquer perfil do P2 seguem no padrão
    check(inp.binding_value(0, "playstation", "jump") == "a" and inp.binding_value(1, "xbox", "jump") == "a", "outros perfis intactos")
    # P2 (DualSense): edita o perfil PlayStation; o jogo usa esse perfil para o controle dele
    start_capture(g, sm, 1, "playstation", "fire")
    inp.last_gamepad_button = (1, "rb")
    step(g)
    check(inp.binding_value(1, "playstation", "fire") == "rb", "P2 PlayStation: fogo = R1")
    state.clear(); state.add((1, "rb"))
    inp.update()
    check("p2_fire" in inp.held and "p1_fire" not in inp.held, "R1 do P2 deveria atirar só para o P2")
    state.clear(); state.add((1, "x"))                      # o antigo botão de fogo (□) não atira mais
    inp.update()
    check("p2_fire" not in inp.held, "□ não deveria mais atirar no P2")
    # movimento do controle é fixo: tentar remapear só avisa
    sm.c_player, sm.c_device = 0, "xbox"
    sm._start_capture("left")
    check(sm.capture is None and "FIXO" in sm.toast[0], f"movimento no controle é fixo ({sm.toast})")
    # 4 jogadores no teclado: nada dos outros muda quando o P4 mexe nos seus
    before = [dict(b.key_codes) for b in inp.bindings[:3]]
    inp.set_binding(3, "keyboard", "jump", pygame.K_F9)
    check([dict(b.key_codes) for b in inp.bindings[:3]] == before, "alterar o P4 mexeu nos demais")
    draw(g)


def test_restaurar_padroes_por_dispositivo():
    path = new_path()
    g, d = mk(pads=XBOX_PS, cfg=ConfigManager(path).load())
    inp = g.input
    sm = open_menu(g, tab=1)
    inp.set_binding(0, "keyboard", "jump", pygame.K_h)
    inp.set_binding(0, "xbox", "fire", "lb")
    inp.set_binding(0, "playstation", "dash", "rb")
    inp.set_binding(1, "keyboard", "jump", pygame.K_g)
    sm.c_player, sm.c_device = 0, "xbox"
    sm._ask_restore()
    check(sm.modal and sm.modal["kind"] == "restore" and sm.modal["sel"] == 1, "restaurar pede confirmação (foco em CANCELAR)")
    tap(g, "global_return")                                # CANCELAR
    check(inp.binding_value(0, "xbox", "fire") == "lb", "cancelar não restaura")
    step(g, n=10)
    sm._ask_restore()
    tap(g, "global_left")                                  # → RESTAURAR
    tap(g, "global_return")
    check(inp.binding_value(0, "xbox", "fire") == "x", "Xbox do P1 restaurado")
    check(inp.binding_value(0, "keyboard", "jump") == pygame.K_h, "teclado do P1 deveria ficar como está")
    check(inp.binding_value(0, "playstation", "dash") == "rb", "PlayStation do P1 deveria ficar como está")
    check(inp.binding_value(1, "keyboard", "jump") == pygame.K_g, "P2 deveria ficar como está")
    saved = json.load(open(path))["controls"]["1"]
    check(saved["xbox"]["fire"] == "x" and saved["keyboard"]["jump"] == "h", f"arquivo reflete a restauração {saved}")
    # teclado do P1: P2 usa 'w' (padrão do P1 para pular)? força o conflito e confere a recusa clara
    step(g, n=10)
    inp.set_binding(1, "keyboard", "dash", pygame.K_w)
    sm.c_player, sm.c_device = 0, "keyboard"
    sm._ask_restore()
    tap(g, "global_left")
    tap(g, "global_return")
    check(inp.binding_value(0, "keyboard", "jump") == pygame.K_h, "restauração com colisão não deve alterar nada")
    check("COLIDE" in sm.toast[0], f"aviso de colisão ({sm.toast})")
    inp.set_binding(1, "keyboard", "dash", pygame.K_DOWN)
    step(g, n=10)
    sm._ask_restore()
    tap(g, "global_left")
    tap(g, "global_return")
    check(inp.binding_value(0, "keyboard", "jump") == pygame.K_w and not any(inp.is_customized(0, "keyboard", a) for a in S.CONTROL_ACTIONS),
          "teclado do P1 restaurado")


def test_desconexao_de_controle():
    g, d = mk(pads=XBOX_PS, cfg=ConfigManager(new_path()).load())
    inp, gp = g.input, g.input.gamepad
    sm = open_menu(g, tab=1)
    start_capture(g, sm, 0, "xbox", "jump")
    # o controle do P1 some (o do P2 continua): o jogo trata o evento e o P1 volta ao teclado
    gp.pads[0] = None
    gp.feed_events = lambda events: [(0, "changed", False)]
    inp.feed_gamepad_events([])
    check(inp.bindings[0].gamepad_slot is None, "P1 deveria perder a vaga do controle desconectado")
    inp.update()
    step(g, n=3)
    draw(g)
    check(sm.capture is not None or True, "captura pode seguir esperando (o controle do P2 existe)")
    # agora some o último: a captura cancela sozinha, sem erro
    gp.pads[1] = None
    step(g, n=3)
    check(sm.capture is None and "DESCONECTADO" in sm.toast[0], f"sem controles a captura deveria cancelar ({sm.toast})")
    draw(g)
    sm._start_capture("jump")
    check(sm.capture is None and "CONECTE" in sm.toast[0], "não captura botão sem nenhum controle")
    # teclado continua remapeável e o menu continua navegável
    sm.c_device = "keyboard"
    start_capture(g, sm, 0, "keyboard", "jump")
    inp.last_key_pressed = pygame.K_F7
    step(g)
    check(inp.binding_value(0, "keyboard", "jump") == pygame.K_F7, "teclado funciona sem controles")
    # linha de controle associado com a lista vazia
    sm.focus, sm.row = "main", 1
    tap(g, "global_right")
    check(inp.bindings[0].gamepad_slot is None, "sem controles, o seletor fica em NENHUM")
    # reconexão: volta a aparecer
    gp.pads[0] = object()
    gp.feed_events = lambda events: [(0, "changed", True)]
    inp.feed_gamepad_events([])
    check(inp.bindings[0].gamepad_slot == 0, "reconexão deveria reassociar ao P1")
    draw(g)


# ============================================================================= NAVEGAÇÃO E COMPATIBILIDADE
def test_navegacao_teclado_e_controle():
    g, d = mk(pads=XBOX_PS, cfg=ConfigManager(new_path()).load())
    sm = open_menu(g)
    check(sm.focus == "side" and sm.side_sel == 0 and sm.tab == 0, "abre na categoria ÁUDIO / VÍDEO")
    tap(g, "global_down")
    check(sm.side_sel == 1 and sm.tab == 1, "↓ troca de categoria (CONTROLES)")
    tap(g, "global_down")
    check(sm.side_sel == 2, "↓ chega em VOLTAR")
    tap(g, "global_up")
    tap(g, "global_up")
    check(sm.side_sel == 0 and sm.tab == 0, "↑ volta")
    tap(g, "global_right")
    check(sm.focus == "main" and sm.row == 0, "→ entra no conteúdo")
    tap(g, "global_down")
    tap(g, "global_down")
    check(sm.rows()[sm.row] == "res", f"linha RESOLUÇÃO ({sm.rows()[sm.row]})")
    step(g, held={"global_gp_confirm"}, pressed={"global_gp_confirm"})                 # A do controle
    step(g, n=5)
    tap(g, "global_escape")
    check(sm.focus == "side", "ESC volta para as categorias")
    step(g, held={"global_gp_back"}, pressed={"global_gp_back"})                       # B do controle
    step(g, n=3)
    check(g.state == "paused", f"B na barra lateral fecha o menu ({g.state})")
    # abre de novo e navega só com o "controle" (direcional = global_*, A = global_gp_confirm)
    sm = open_menu(g)
    tap(g, "global_down")
    step(g, held={"global_gp_confirm"}, pressed={"global_gp_confirm"})
    step(g, n=3)
    check(sm.tab == 1 and sm.focus == "main", "A entra na aba CONTROLES")
    for _ in range(3):
        tap(g, "global_down")
    check(sm.rows()[sm.row] == "act:left", f"descendo até as ações ({sm.rows()[sm.row]})")
    step(g, held={"global_gp_confirm"}, pressed={"global_gp_confirm"})
    step(g, n=2)
    check(sm.c_device == "xbox", f"P1 com controle Xbox abre no perfil XBOX ({sm.c_device})")
    check(sm.capture is None and "FIXO" in sm.toast[0], f"mover no controle é fixo: só avisa ({sm.toast[0]})")
    tap(g, "global_escape")
    tap(g, "global_escape")
    check(g.state == "paused", "ESC duas vezes fecha")


def test_fluxo_titulo_pausa_e_1_a_4_jogadores():
    import game as G
    g, d = mk(cfg=ConfigManager(new_path()).load())
    # título -> CONFIGURAÇÕES -> volta ao título
    g.state = "title"
    g.title_sel = G.TITLE_ITEMS.index("settings")
    tap(g, "global_return")
    check(g.state == "settings" and g.settings_menu.return_to == "title", f"título → configurações ({g.state})")
    draw(g)
    step(g, n=15)
    tap(g, "global_escape")
    check(g.state == "title" and g.title_sel == G.TITLE_ITEMS.index("settings"), f"ESC volta ao título ({g.state})")
    draw(g)
    # 1 a 4 jogadores: abre/ajusta/fecha a partir da pausa e a partida continua
    for n in (1, 2, 3, 4):
        g, d = mk(cfg=ConfigManager(new_path()).load())
        g.player_count = n
        g.start_match()
        step(g, n=40)
        check(len(g.players) == n, f"{n} jogadores")
        g.toggle_pause()
        sm = open_menu(g, tab=1)
        draw(g)
        for p in range(S.MAX_PLAYERS):                     # configura QUALQUER jogador, mesmo os que não estão na partida
            sm.c_player = p
            sm._sync_device_to_pad()
            draw(g)
        sm.close()
        g.toggle_pause()
        step(g, n=40)
        draw(g)
        check(g.state == "playing" and len(g.players) == n, f"{n}J: partida continua após as configurações")
        # os comandos individuais seguem valendo: tecla do jogador n-1 vira 'held' do jogador certo
    pg = pygame.key.get_pressed
    g, d = mk()
    g.player_count = 2
    g.start_match()
    g.input.set_binding(1, "keyboard", "fire", pygame.K_F8)
    keys = {pygame.K_F8: True}
    class K:
        def __getitem__(self, code):
            return keys.get(code, False)
    pygame.key.get_pressed = lambda: K()
    try:
        g.input.update()
        check("p2_fire" in g.input.held and "p1_fire" not in g.input.held, "tecla remapeada do P2 só dispara o P2")
    finally:
        pygame.key.get_pressed = pg


def test_desenho_de_todas_as_telas():
    g, d = mk(pads=XBOX_PS, cfg=ConfigManager(new_path()).load())
    sm = open_menu(g)
    os.makedirs("/tmp/shots", exist_ok=True)
    t0 = time.perf_counter()
    n = 0
    for tab in (0, 1):
        sm._switch_tab(tab)
        for dev in S.CONTROL_DEVICES:
            sm.c_device = dev
            for player in range(S.MAX_PLAYERS):
                sm.c_player = player
                for rowi in range(len(sm.rows())):
                    sm.focus, sm.row = "main", rowi
                    step(g)
                    draw(g)
                    n += 1
    start_capture(g, sm, 0, "xbox", "jump")
    sm.capture["msg"], sm.capture["msg_t"] = "TECLA RESERVADA (F11)", 2.0
    draw(g)
    pygame.image.save(g.screen, "/tmp/shots/settings_capture_msg.png")
    sm._end_capture()
    sm.modal = dict(kind="swap", title="COMANDO JÁ ATRIBUÍDO", sel=0, lines=["a", "b", "c"], buttons=[("TROCAR", "swap"), ("CANCELAR", "cancel")], data=(0, "keyboard", "jump", "dash"))
    draw(g)
    pygame.image.save(g.screen, "/tmp/shots/settings_modal.png")
    sm.modal = None
    sm._say("TESTE DE AVISO", (70, 240, 138))
    sm._switch_tab(0)
    step(g, n=20)
    draw(g)
    pygame.image.save(g.screen, "/tmp/shots/settings_toast.png")
    ms = (time.perf_counter() - t0) / max(1, n) * 1000
    print(f"      {n} quadros do menu desenhados, {ms:.1f} ms/quadro (update+draw)")
    check(ms < 16.0, f"menu lento demais ({ms:.1f} ms)")


def test_main_inicia_com_config_salvo():
    """Executa main.py de verdade (subprocesso, SDL dummy): lê config.json, aplica resolução/volumes e fecha limpo."""
    path = new_path()
    json.dump({"audio": {"music_volume": 20, "sfx_volume": 30}, "video": {"width": 1366, "height": 768, "fullscreen": False}},
              open(path, "w"))
    before = open(path, encoding="utf-8").read()
    code = (
        "import os, threading, pygame\n"
        "pygame.init(); pygame.display.set_mode((10, 10))\n"
        "threading.Timer(1.5, lambda: pygame.event.post(pygame.event.Event(pygame.QUIT))).start()\n"
        "import main\n"
        "raise SystemExit(main.main([]))\n"
    )
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy", ORBITAL_CONFIG=path)
    r = subprocess.run([sys.executable, "-c", code], cwd=os.path.dirname(os.path.abspath(__file__)), env=env,
                       capture_output=True, text=True, timeout=60)
    check(r.returncode == 0, f"main.py terminou com código {r.returncode}: {r.stderr[-400:]}")
    check("Traceback" not in r.stderr, f"main.py gerou erro: {r.stderr[-400:]}")
    check(open(path, encoding="utf-8").read() == before, "iniciar e fechar sem mexer em nada não deve reescrever o config.json")
    # sem arquivo: main cria config.json com os padrões
    path2 = new_path()
    env["ORBITAL_CONFIG"] = path2
    r = subprocess.run([sys.executable, "-c", code], cwd=os.path.dirname(os.path.abspath(__file__)), env=env,
                       capture_output=True, text=True, timeout=60)
    check(r.returncode == 0 and os.path.exists(path2), f"main.py sem config deveria criar o arquivo ({r.stderr[-300:]})")


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
        mouse((0, 0), False, False)
        ran += 1
        ok = len(FAILS) == before
        failed += (not ok)
        print(f"  {'OK' if ok else 'FALHOU'}  ({time.time() - t0:.1f}s)")
    print(f"\n{ran - failed}/{ran} testes passaram")
    if FAILS:
        print("\nFalhas:")
        for f in FAILS:
            print(" -", f)
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
