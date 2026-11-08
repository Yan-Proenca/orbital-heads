"""
display.py — janela, resolução e tela cheia do ORBITAL HEADS.

O jogo inteiro (física, HUD, menus, 4 jogadores) usa coordenadas LÓGICAS fixas de 1280x720 (settings.WIDTH/HEIGHT).
Em vez de reescrever tudo para N resoluções, o jogo desenha numa "tela lógica" (`canvas`) e este módulo a ESCALA
para a janela na resolução escolhida:

    Game.draw(display.canvas)  ->  display.present()  ->  [escala 1280x720 -> janela]  ->  flip

* Proporção preservada: a imagem nunca é esticada. Se o monitor/janela não for 16:9, aparecem barras pretas
  (letterbox/pillarbox). Posições relativas de jogadores, inimigos e projéteis ficam idênticas em qualquer resolução.
* Resoluções oferecidas = candidatas de settings.RESOLUTION_CANDIDATES que o monitor suporta (tamanho do desktop
  + pygame.display.list_modes() em tela cheia) + modos 16:9 extras reportados pelo pygame. 1280x720 sempre existe.
* Qualidade: escalas não-inteiras usam smoothscale (suave) e escalas inteiras usam scale (pixels nítidos). O jogo
  pode desligar o suave quando o FPS cai (`display.smooth = False`), trocando qualidade por ~4 ms/quadro.
* Mouse: `to_logical()` converte a posição na janela para a tela lógica (menus clicáveis em qualquer resolução).
* Trocar resolução/tela cheia é só um novo set_mode: a partida, os objetos e o loop principal não são tocados.
"""
import pygame

import settings as S


class DisplayManager:
    def __init__(self, logical=(S.WIDTH, S.HEIGHT)):
        self.logical = (int(logical[0]), int(logical[1]))
        self.canvas = pygame.Surface(self.logical)     # vira o formato da janela no 1º apply()
        self.window = None
        self.size = self.logical
        self.fullscreen = False
        self.scale = 1.0
        self.view = pygame.Rect(0, 0, *self.logical)   # onde a imagem aparece dentro da janela
        self.smooth = True
        self._buf = None
        self._bars = []

    # ------------------------------------------------------------ consulta ao sistema
    def desktop_size(self):
        """Tamanho do desktop (monitor principal)."""
        try:
            sizes = pygame.display.get_desktop_sizes()
            if sizes:
                return (int(sizes[0][0]), int(sizes[0][1]))
        except (pygame.error, AttributeError):
            pass
        try:
            info = pygame.display.Info()
            if info.current_w > 0 and info.current_h > 0:
                return (info.current_w, info.current_h)
        except pygame.error:
            pass
        return self.logical

    def supported_modes(self):
        """Modos de tela cheia que o pygame lista; None = 'qualquer tamanho serve'; [] = não informou."""
        try:
            modes = pygame.display.list_modes()
        except pygame.error:
            return []
        if modes == -1:
            return None
        return [(int(w), int(h)) for (w, h) in modes]

    def is_supported(self, size, fullscreen):
        """Janela: qualquer tamanho que caiba no desktop (o tamanho nativo do jogo, 1280x720, sempre vale).
        Tela cheia: só modos que o monitor realmente lista em pygame.display.list_modes() ou o tamanho nativo
        do desktop — nunca assume que todo monitor aceita todas as resoluções."""
        size = (int(size[0]), int(size[1]))
        dw, dh = self.desktop_size()
        if not fullscreen:
            return size == self.logical or (size[0] <= dw and size[1] <= dh)
        if size == (dw, dh):
            return True
        if size[0] > dw or size[1] > dh:
            return False
        modes = self.supported_modes()
        return modes is None or size in modes

    def available_resolutions(self, fullscreen=None):
        """Resoluções para o seletor, em ordem crescente, já filtradas pelo que o dispositivo suporta."""
        fs = self.fullscreen if fullscreen is None else fullscreen
        out = [s for s in S.RESOLUTION_CANDIDATES if self.is_supported(s, fs)]
        modes = self.supported_modes() or []
        mw, mh = S.RESOLUTION_MAX
        for (w, h) in modes:
            if w <= mw and h <= mh and w >= self.logical[0] and h >= self.logical[1] \
                    and abs(w / h - self.logical[0] / self.logical[1]) < 0.02 and (w, h) not in out \
                    and self.is_supported((w, h), fs):
                out.append((w, h))
        if fs:
            desk = self.desktop_size()          # o modo nativo do monitor é sempre uma opção segura em tela cheia
            if desk not in out and desk[0] <= mw and desk[1] <= mh:
                out.append(desk)
        elif self.logical not in out:
            out.append(self.logical)
        return sorted(set(out)) or [self.logical]

    def nearest(self, size, fullscreen=None):
        """Resolução suportada mais próxima de `size`."""
        options = self.available_resolutions(fullscreen)
        return min(options, key=lambda s: abs(s[0] - size[0]) + abs(s[1] - size[1]))

    # ------------------------------------------------------------ aplicar
    def apply(self, size, fullscreen):
        """Cria/recria a janela. Nunca levanta: se o modo pedido falhar, cai para um modo seguro.
        Devolve dict(size, fullscreen, ok, note) com o que realmente ficou ativo."""
        want = (int(size[0]), int(size[1]))
        note, ok = "", True
        if not self.is_supported(want, fullscreen):
            alt = self.nearest(want, fullscreen)
            note = f"RESOLUÇÃO NÃO SUPORTADA — USANDO {alt[0]}×{alt[1]}"
            want, ok = alt, False
        flags = pygame.FULLSCREEN if fullscreen else 0
        try:
            self.window = pygame.display.set_mode(want, flags)
            if not fullscreen and self.window.get_size() != want:
                # Ao sair da tela cheia o SDL pode manter o tamanho antigo na 1ª chamada: repete uma vez.
                self.window = pygame.display.set_mode(want, flags)
        except pygame.error:
            ok = False
            note = "FALHA AO MUDAR O MODO DE VÍDEO — MODO JANELA SEGURO"
            fullscreen, want = False, self.logical
            self.window = pygame.display.set_mode(want)
        self.size = self.window.get_size()
        self.fullscreen = bool(fullscreen and (self.window.get_flags() & pygame.FULLSCREEN))
        if self.canvas.get_bitsize() != self.window.get_bitsize():
            self.canvas = self.canvas.convert(self.window)
        elif not getattr(self, "_converted", False):
            self.canvas = self.canvas.convert()
        self._converted = True
        self._layout()
        pygame.mouse.set_visible(False)                # o cursor do jogo é desenhado pelos menus (MenuInput)
        return dict(size=self.size, fullscreen=self.fullscreen, ok=ok, note=note)

    def toggle_fullscreen(self):
        """Alterna tela cheia preservando a resolução escolhida."""
        return self.apply(self.size, not self.fullscreen)

    def _layout(self):
        lw, lh = self.logical
        w, h = self.size
        self.scale = min(w / lw, h / lh)
        vw, vh = int(round(lw * self.scale)), int(round(lh * self.scale))
        self.view = pygame.Rect((w - vw) // 2, (h - vh) // 2, vw, vh)
        self._buf = None if (vw, vh) == (lw, lh) else pygame.Surface((vw, vh), 0, self.canvas)
        bars = []
        v = self.view
        if v.left > 0:
            bars += [pygame.Rect(0, 0, v.left, h), pygame.Rect(v.right, 0, w - v.right, h)]
        if v.top > 0:
            bars += [pygame.Rect(0, 0, w, v.top), pygame.Rect(0, v.bottom, w, h - v.bottom)]
        self._bars = bars
        if self.window is not None:
            self.window.fill((0, 0, 0))

    # ------------------------------------------------------------ quadro
    def present(self):
        """Escala o canvas para a janela (com barras se preciso) e mostra o quadro."""
        win = self.window
        if self._buf is None:
            win.blit(self.canvas, self.view.topleft)
        else:
            integer = abs(self.scale - round(self.scale)) < 0.01
            if self.smooth and not integer:
                pygame.transform.smoothscale(self.canvas, self.view.size, self._buf)
            else:
                pygame.transform.scale(self.canvas, self.view.size, self._buf)
            for bar in self._bars:
                win.fill((0, 0, 0), bar)
            win.blit(self._buf, self.view.topleft)
        pygame.display.flip()

    def to_logical(self, pos):
        """Posição na janela -> posição na tela lógica 1280x720 (limitada às bordas)."""
        if self.scale <= 0:
            return (int(pos[0]), int(pos[1]))
        x = (pos[0] - self.view.left) / self.scale
        y = (pos[1] - self.view.top) / self.scale
        return (int(max(0, min(self.logical[0] - 1, x))), int(max(0, min(self.logical[1] - 1, y))))
