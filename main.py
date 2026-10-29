#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py — ponto de entrada do ORBITAL HEADS (versão Pygame).

    python main.py
    python main.py --fullscreen

Responsabilidades deste arquivo, e só deste arquivo:
  - inicializar o pygame (vídeo, mixer, joystick);
  - abrir a janela e manter o loop principal a 60 FPS com delta time;
  - repassar eventos do SO para o InputManager;
  - chamar Game.step(dt) e Game.draw(surface) a cada quadro.

Toda a lógica de jogo vive em game.py / player.py / enemy.py / audio.py /
input_handler.py — main.py não conhece regras do jogo, só orquestra o loop.
"""
import sys

import pygame

import settings as S
from game import Game


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    fullscreen = "--fullscreen" in argv

    pygame.init()                      # inicializa vídeo, eventos, etc. (mixer é feito à parte em AudioManager)
    pygame.joystick.init()

    flags = pygame.FULLSCREEN if fullscreen else 0
    screen = pygame.display.set_mode((S.WIDTH, S.HEIGHT), flags)
    pygame.display.set_caption("ORBITAL HEADS - 2 jogadores")
    # O cursor do SO fica oculto; MenuInput desenha seu próprio cursor nas
    # telas de menu (título, dificuldade, pausa), e nenhum cursor aparece
    # durante o jogo em si (onde o mouse não controla nada).
    pygame.mouse.set_visible(False)

    clock = pygame.time.Clock()
    game = Game(screen)

    running = True
    while running:
        # --- dt em segundos, travado para evitar saltos grandes (alt-tab, breakpoint, etc.)
        raw_dt = clock.tick(S.FPS) / 1000.0
        dt = min(S.MAX_DT, raw_dt)

        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                running = False
            game.input.handle_event(event)
        # GamepadManager consome a MESMA lista (nunca chama pygame.event.get()
        # por conta própria), para não competir pela fila de eventos do pygame.
        game.input.feed_gamepad_events(events)

        game.input.update()

        try:
            game.step(dt)
        except Exception:
            import traceback
            traceback.print_exc()
            # um erro isolado não deve derrubar a partida inteira em produção;
            # durante o desenvolvimento, prefira deixar a exceção propagar.

        game.draw(screen)
        pygame.display.flip()

        if not game.running:
            running = False

    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
