"""
menu_input.py — navegação de menus por teclado, MOUSE e CONTROLE
(Xbox/PlayStation), tudo junto. Isso cobre o item 4 do pedido ("navegar o
menu com o cursor do mouse e com o controle do Xbox") sem duplicar a lógica
de cada tela de menu em game.py.

Como funciona:
  - MenuInput.update(dt) é chamado uma vez por quadro, ANTES de qualquer
    tela de menu ser desenhada. Ele lê a posição do mouse, os cliques, e o
    analógico/D-pad de qualquer joystick conectado, convertendo tudo em:
        nav_delta()        -> -1 / 0 / +1 (mover a seleção para cima/baixo),
                               com repetição automática enquanto se segura
                               uma tecla, o analógico ou o D-pad;
        hovered_index       -> índice do item sob o cursor do mouse (ou None);
        confirm_clicked     -> True no quadro em que o botão A/Cross ou o
                               clique esquerdo confirmou um item;
        draw_cursor(surf)   -> desenha um cursor de mouse visível por cima
                               de tudo, para o jogador saber onde está.
  - Cada tela de menu em game.py chama `register_hit_areas([...])` com os
    retângulos (pygame.Rect) de cada item, na ORDEM em que aparecem na
    tela, logo depois de desenhá-los. Isso é o que permite ao mouse saber
    sobre qual item ele está pairando.

O controle Xbox usa o analógico esquerdo (eixo Y) e o D-pad (hat) para
cima/baixo, e o botão A (índice 0, settings.GAMEPAD_BUTTONS['confirm'])
para confirmar — o mesmo botão usado para pular durante o jogo, o que é o
padrão esperado em jogos de console.
"""
import pygame

import settings as S


class MenuInput:
    def __init__(self, input_manager):
        self.input = input_manager
        self.hovered_index = None
        self.confirm_clicked = False
        self.back_clicked = False      # botão B/Circle do controle, ou clique direito do mouse
        self._hit_areas = []
        self._extra_hit_areas = []     # [(pygame.Rect, índice_arbitrário), ...], ver register_extra_hit_areas
        self._axis_dir = 0          # -1/0/1: direção atualmente "segurada" no analógico/D-pad
        self._axis_timer = 0.0
        self._mouse_pos = (0, 0)
        self._mouse_moved_this_frame = False
        self._prev_mouse_buttons = (False, False, False)
        self._prev_gamepad_confirm = False
        self._prev_gamepad_back = False
        self._cursor_visible = True

    def reset_hover(self):
        """Chamado ao entrar numa tela de menu nova, para não herdar o hover da tela anterior."""
        self.hovered_index = None
        self._hit_areas = []
        self._extra_hit_areas = []
        self._axis_dir = 0
        self._axis_timer = 0.0

    # ------------------------------------------------------------ atualização por quadro
    def update(self, dt):
        self.confirm_clicked = False
        self.back_clicked = False
        self._update_mouse()
        self._update_gamepad_and_keyboard_nav(dt)

    def _update_mouse(self):
        pos = pygame.mouse.get_pos()
        self._mouse_moved_this_frame = pos != self._mouse_pos
        self._mouse_pos = pos
        buttons = pygame.mouse.get_pressed(num_buttons=3)
        left_click = buttons[0] and not self._prev_mouse_buttons[0]
        right_click = buttons[2] and not self._prev_mouse_buttons[2]
        self._prev_mouse_buttons = buttons
        if self._mouse_moved_this_frame:
            self._cursor_visible = True
            self.hovered_index = self._hit_test(pos)
        if left_click:
            self._cursor_visible = True
            idx = self._hit_test(pos)
            if idx is not None:
                self.hovered_index = idx
                self.confirm_clicked = True
        if right_click:
            self._cursor_visible = True
            self.back_clicked = True

    def _hit_test(self, pos):
        # áreas extras primeiro (abas, botões de rodapé com índice arbitrário/negativo):
        # permitem que uma tela de menu tenha "zonas" fora da lista principal
        # de itens navegáveis por ↑/↓ (ex.: abas de jogador navegadas por ←/→).
        for rect, idx in self._extra_hit_areas:
            if rect.collidepoint(pos):
                return idx
        for i, rect in enumerate(self._hit_areas):
            if rect.collidepoint(pos):
                return i
        return None

    def _update_gamepad_and_keyboard_nav(self, dt):
        """Analógico/D-pad de QUALQUER controle conectado + teclado (setas), com
        repetição: o primeiro passo é imediato, os seguintes respeitam
        MENU_AXIS_REPEAT_DELAY/RATE enquanto a direção continua segurada."""
        direction = 0
        # teclado: já vem resolvido em input.held como global_up/global_down
        if "global_down" in self.input.held:
            direction = 1
        elif "global_up" in self.input.held:
            direction = -1
        # controles: olha o analógico esquerdo (eixo Y) e o D-pad de QUALQUER controle
        # conectado, via GamepadManager (já trata Xbox/PlayStation/Switch/genérico).
        if direction == 0:
            gp = self.input.gamepad
            for i in range(gp.count):
                if not gp.is_connected(i):
                    continue
                _, dy = gp.axis_dir(i, deadzone=S.JOYSTICK_DEADZONE)
                if dy != 0:
                    direction = dy
                    break

        self._nav_pulse = 0
        if direction == 0:
            self._axis_dir = 0
            self._axis_timer = 0.0
        elif direction != self._axis_dir:
            self._axis_dir = direction
            self._axis_timer = S.MENU_AXIS_REPEAT_DELAY
            self._nav_pulse = direction
        else:
            self._axis_timer -= dt
            if self._axis_timer <= 0:
                self._axis_timer = S.MENU_AXIS_REPEAT_RATE
                self._nav_pulse = direction

        # confirmar com o botão A/Cross de qualquer controle (equivalente ao Enter/clique);
        # voltar/cancelar com o botão B/Circle.
        gp = self.input.gamepad
        confirm_now = any(gp.is_connected(i) and gp.button_down(i, S.GAMEPAD_BUTTONS["confirm"])
                           for i in range(gp.count))
        back_now = any(gp.is_connected(i) and gp.button_down(i, S.GAMEPAD_BUTTONS["back"])
                        for i in range(gp.count))
        if confirm_now and not self._prev_gamepad_confirm:
            self.confirm_clicked = True
            self._cursor_visible = False     # navegando por controle: some com o cursor do mouse
        if back_now and not self._prev_gamepad_back:
            self.back_clicked = True
            self._cursor_visible = False
        self._prev_gamepad_confirm = confirm_now
        self._prev_gamepad_back = back_now
        if direction != 0:
            self._cursor_visible = False     # navegando por teclado/controle: some com o cursor do mouse

    def nav_delta(self):
        """-1 (subir) / 0 (nada) / +1 (descer) — já com a repetição aplicada. Também
        limpa o hover do mouse quando há navegação por teclado/controle, para a
        seleção visual não ficar "presa" embaixo do cursor parado."""
        pulse = getattr(self, "_nav_pulse", 0)
        if pulse:
            self.hovered_index = None
        return pulse

    # ------------------------------------------------------------ usado pelas telas de menu
    def register_hit_areas(self, rects):
        """Chamado pela tela de menu logo após desenhar seus itens, na mesma ordem
        em que aparecem na lista de seleção (PAUSE_ITEMS, DIFFICULTY_ORDER, ...)."""
        self._hit_areas = list(rects)

    def register_extra_hit_areas(self, pairs):
        """Áreas de clique com índice PRÓPRIO (não sequencial), para zonas de uma
        tela que não fazem parte da navegação ↑/↓ principal — por exemplo as
        abas de jogador na tela de configuração de controles, navegadas por
        ←/→ e identificadas por hovered_index negativo para não colidir com
        os índices (sempre ≥ 0) de register_hit_areas. `pairs` é uma lista de
        (pygame.Rect, índice)."""
        self._extra_hit_areas = list(pairs)

    def draw_cursor(self, surf):
        if not self._cursor_visible:
            return
        x, y = self._mouse_pos
        pts = [(x, y), (x, y + 18), (x + 5, y + 14), (x + 8, y + 21),
               (x + 11, y + 20), (x + 8, y + 13), (x + 13, y + 13)]
        pygame.draw.polygon(surf, (255, 255, 255), pts)
        pygame.draw.polygon(surf, (10, 10, 20), pts, width=1)
