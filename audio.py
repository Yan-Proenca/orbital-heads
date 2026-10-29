"""
audio.py — gerenciador de áudio (BGM + SFX) usando pygame.mixer.

Uso típico:
    audio = AudioManager()
    audio.load_all()
    audio.play_music("gameplay")
    audio.play_sfx("shoot")
    audio.toggle_music()          # liga/desliga a trilha (menu de pausa)
    audio.set_sfx_volume(0.6)

O gerenciador é tolerante a assets ausentes: se um arquivo .ogg/.wav não
existir em assets/sfx ou assets/music, ele registra um aviso uma única vez
e segue sem travar o jogo (útil durante o desenvolvimento, antes de todos
os sons finais estarem prontos).
"""
import os
import pygame

import settings as S


class AudioManager:
    def __init__(self):
        self._sfx = {}              # nome -> pygame.mixer.Sound
        self._music_tracks = {}     # nome -> caminho do arquivo (musica e streamada, nao pre-carregada)
        self._current_music = None
        self.music_enabled = True
        self.sfx_enabled = True
        self.music_volume = S.DEFAULT_MUSIC_VOLUME
        self.sfx_volume = S.DEFAULT_SFX_VOLUME
        self._missing_warned = set()
        self._channel_cooldown = {}     # evita 30 explosões simultâneas estourando o volume
        self._mixer_ok = False

    # ------------------------------------------------------------ setup
    def init_mixer(self):
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            pygame.mixer.set_num_channels(32)
            self._mixer_ok = True
        except pygame.error as exc:
            print("[audio] mixer indisponível (sem dispositivo de áudio?):", exc)
            self._mixer_ok = False

    def load_all(self):
        """Carrega todos os SFX definidos em settings; a música é tocada via stream (não precisa de load)."""
        if not self._mixer_ok:
            return
        for name, filename in S.SFX_FILES.items():
            path = os.path.join(S.SFX_DIR, filename)
            if not os.path.isfile(path):
                self._warn_missing(path)
                continue
            try:
                snd = pygame.mixer.Sound(path)
                snd.set_volume(self.sfx_volume)
                self._sfx[name] = snd
            except pygame.error as exc:
                print(f"[audio] falha ao carregar SFX '{name}' ({path}):", exc)
        for name, filename in S.MUSIC_FILES.items():
            path = os.path.join(S.MUSIC_DIR, filename)
            if os.path.isfile(path):
                self._music_tracks[name] = path
            else:
                self._warn_missing(path)

    def _warn_missing(self, path):
        if path not in self._missing_warned:
            self._missing_warned.add(path)
            print(f"[audio] asset ausente (ok durante o desenvolvimento): {path}")

    # ------------------------------------------------------------ SFX
    def play_sfx(self, name, volume_scale=1.0, cooldown=0.0):
        """Toca um efeito sonoro pelo nome lógico (ver settings.SFX_FILES).
        cooldown evita que o mesmo som dispare dezenas de vezes no mesmo quadro
        (ex.: várias explosões simultâneas) — opcional, em segundos de jogo real."""
        if not (self._mixer_ok and self.sfx_enabled):
            return
        snd = self._sfx.get(name)
        if snd is None:
            return
        if cooldown > 0:
            now = pygame.time.get_ticks() / 1000.0
            last = self._channel_cooldown.get(name, -999)
            if now - last < cooldown:
                return
            self._channel_cooldown[name] = now
        snd.set_volume(self.sfx_volume * volume_scale)
        snd.play()

    def set_sfx_volume(self, vol):
        self.sfx_volume = max(0.0, min(1.0, vol))
        for snd in self._sfx.values():
            snd.set_volume(self.sfx_volume)

    def toggle_sfx(self):
        self.sfx_enabled = not self.sfx_enabled

    # ------------------------------------------------------------ BGM
    def play_music(self, name, loop=True, fade_ms=400):
        if not self._mixer_ok:
            return
        path = self._music_tracks.get(name)
        self._current_music = name
        if path is None:
            return
        if not self.music_enabled:
            return
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self.music_volume)
            pygame.mixer.music.play(-1 if loop else 0, fade_ms=fade_ms)
        except pygame.error as exc:
            print(f"[audio] falha ao tocar música '{name}':", exc)

    def stop_music(self, fade_ms=300):
        if self._mixer_ok:
            pygame.mixer.music.fadeout(fade_ms)

    def toggle_music(self):
        """Liga/desliga a trilha sonora (usado no menu de pausa/configurações)."""
        self.music_enabled = not self.music_enabled
        if not self._mixer_ok:
            return
        if self.music_enabled:
            if self._current_music:
                self.play_music(self._current_music, fade_ms=200)
        else:
            pygame.mixer.music.fadeout(200)
        return self.music_enabled

    def set_music_volume(self, vol):
        self.music_volume = max(0.0, min(1.0, vol))
        if self._mixer_ok:
            pygame.mixer.music.set_volume(self.music_volume)

    # ------------------------------------------------------------ eventos de jogo (conveniência)
    # Estes métodos dão nomes "de domínio" às chamadas de SFX, para o resto do
    # código não precisar conhecer as chaves cruas de settings.SFX_FILES.
    def on_shoot(self, weapon_key):
        sfx = {"rifle": "shoot_rifle", "shotgun": "shoot_shotgun"}.get(weapon_key, "shoot")
        self.play_sfx(sfx, cooldown=0.02)

    def on_explosion(self, big=False):
        self.play_sfx("explosion_big" if big else "explosion_small", cooldown=0.03)

    def on_player_hit(self):
        self.play_sfx("player_hit")

    def on_player_death(self):
        self.play_sfx("player_death")

    def on_pickup(self, kind, good=True):
        if kind == "weapon":
            self.play_sfx("pickup_weapon")
        else:
            self.play_sfx("pickup_boost_good" if good else "pickup_boost_bad")

    def on_dash(self):
        self.play_sfx("dash", cooldown=0.05)

    def on_jump(self):
        self.play_sfx("jump", cooldown=0.05)

    def on_menu_move(self):
        self.play_sfx("menu_move")

    def on_menu_confirm(self):
        self.play_sfx("menu_confirm")

    def on_round_clear(self):
        self.play_sfx("round_clear")

    def on_boss_warning(self):
        self.play_sfx("boss_warning")

    def on_victory(self):
        self.play_sfx("victory")

    def on_gameover(self):
        self.play_sfx("gameover")
