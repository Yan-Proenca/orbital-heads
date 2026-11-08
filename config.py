"""
config.py — persistência das configurações do jogador em config.json.

Guarda volume da música/efeitos, resolução, tela cheia e os atalhos de cada jogador por dispositivo
(teclado, Xbox, PlayStation). Regras:

  * arquivo ausente   -> cria um config.json com os padrões;
  * JSON inválido     -> usa os padrões SEM impedir o jogo de abrir (o arquivo ruim só é substituído quando
                         o jogador mudar alguma configuração, e antes disso vai uma cópia para config.json.bak);
  * JSON incompleto   -> campos presentes e válidos são aproveitados, o resto vem dos padrões;
  * só reescreve quando algo MUDOU (save() compara com o último conteúdo gravado/lido) e escreve de forma
    atômica (arquivo temporário + os.replace), então um fechamento no meio da gravação não corrompe o arquivo.

path=None cria um gerenciador só em memória (usado por testes e por Game(screen) sem config).
"""
import copy
import json
import os

import settings as S

DEFAULTS = {
    "version": S.CONFIG_VERSION,
    "audio": {"music_volume": int(round(S.DEFAULT_MUSIC_VOLUME * 100)),
              "sfx_volume": int(round(S.DEFAULT_SFX_VOLUME * 100))},
    "video": {"width": S.WIDTH, "height": S.HEIGHT, "fullscreen": False},
    # {"1": {"keyboard": {acao: tecla}, "xbox": {acao: botao}, "playstation": {...}}, "2": ...}; vazio = padrões
    "controls": {},
    # Recordes dos modos de sobrevivência (settings.SURVIVAL_GAME_MODES), um número por modo (0 = nenhum
    # ainda). O campo que cada recorde guarda (tempo/round/wave/level) vem de settings.RECORD_FIELD.
    "records": {mode: 0 for mode in S.SURVIVAL_GAME_MODES},
}


def _num_in(value, lo, hi, default):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        return default
    return int(max(lo, min(hi, round(value))))


def sanitize(raw):
    """Valida a estrutura de um JSON já lido. Devolve (dados_válidos_completos, lista_de_avisos)."""
    data = copy.deepcopy(DEFAULTS)
    issues = []
    if not isinstance(raw, dict):
        return data, ["raiz do JSON não é um objeto"]

    audio = raw.get("audio")
    if isinstance(audio, dict):
        for key in ("music_volume", "sfx_volume"):
            if key in audio:
                v = _num_in(audio[key], 0, 100, None)
                if v is None:
                    issues.append(f"audio.{key} inválido")
                else:
                    data["audio"][key] = v
    elif "audio" in raw:
        issues.append("audio inválido")

    video = raw.get("video")
    if isinstance(video, dict):
        w = _num_in(video.get("width"), 320, 7680, None) if "width" in video else None
        h = _num_in(video.get("height"), 180, 4320, None) if "height" in video else None
        if w is not None and h is not None:
            data["video"]["width"], data["video"]["height"] = w, h
        elif "width" in video or "height" in video:
            issues.append("video.width/height inválidos")
        if "fullscreen" in video:
            if isinstance(video["fullscreen"], bool):
                data["video"]["fullscreen"] = video["fullscreen"]
            else:
                issues.append("video.fullscreen inválido")
    elif "video" in raw:
        issues.append("video inválido")

    controls = raw.get("controls")
    if isinstance(controls, dict):
        valid_actions = set(S.CONTROL_ACTIONS)
        for pkey, pdata in controls.items():
            if not (isinstance(pkey, str) and pkey.isdigit() and 1 <= int(pkey) <= S.MAX_PLAYERS and isinstance(pdata, dict)):
                issues.append(f"controls.{pkey} ignorado")
                continue
            clean = {}
            for dev in S.CONTROL_DEVICES:
                dmap = pdata.get(dev)
                if isinstance(dmap, dict):
                    clean[dev] = {a: v for a, v in dmap.items() if a in valid_actions and isinstance(v, str)}
            data["controls"][pkey] = clean
    elif "controls" in raw:
        issues.append("controls inválido")

    records = raw.get("records")
    if isinstance(records, dict):
        for mode in S.SURVIVAL_GAME_MODES:
            if mode not in records:
                continue
            v = records[mode]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v < 0:
                issues.append(f"records.{mode} inválido")
            else:
                # tempo (Rockets Sky) é float (segundos); os demais são contagens inteiras.
                data["records"][mode] = float(v) if S.RECORD_FIELD.get(mode) == "time" else int(v)
    elif "records" in raw:
        issues.append("records inválido")
    return data, issues


class ConfigManager:
    def __init__(self, path=S.CONFIG_PATH):
        self.path = path
        self.data = copy.deepcopy(DEFAULTS)
        self.status = "memory" if path is None else "defaults"   # memory | created | loaded | invalid | defaults
        self.issues = []
        self._snapshot = self._dump()
        self._corrupt = False
        self._warned = False

    # ------------------------------------------------------------ leitura / escrita
    def _dump(self):
        return json.dumps(self.data, indent=2, ensure_ascii=False)

    def load(self):
        """Lê o arquivo (ou cria o padrão). Nunca levanta exceção: o jogo sempre consegue iniciar."""
        if self.path is None:
            return self
        if not os.path.exists(self.path):
            self.status = "created"
            self.save(force=True)
            return self
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError) as exc:        # ValueError cobre JSONDecodeError e UnicodeDecodeError
            self.status, self._corrupt = "invalid", True
            self.issues = [f"não foi possível ler {os.path.basename(self.path)}: {exc}"]
            self.data = copy.deepcopy(DEFAULTS)
            self._snapshot = self._dump()
            print("[config]", self.issues[0], "- usando padrões")
            return self
        self.data, self.issues = sanitize(raw)
        self.status = "loaded"
        self._snapshot = self._dump()               # nada a gravar até o jogador mudar algo
        for msg in self.issues:
            print("[config] ignorado:", msg)
        return self

    def save(self, force=False):
        """Grava só se mudou (ou force). Devolve True se escreveu."""
        if self.path is None:
            self._snapshot = self._dump()
            return False
        text = self._dump()
        if not force and text == self._snapshot:
            return False
        try:
            folder = os.path.dirname(self.path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            if self._corrupt and os.path.exists(self.path):
                try:
                    os.replace(self.path, self.path + ".bak")     # guarda o arquivo ruim antes de substituí-lo
                except OSError:
                    pass
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, self.path)
        except OSError as exc:
            if not self._warned:
                self._warned = True
                print("[config] não foi possível salvar:", exc)
            return False
        self._snapshot, self._corrupt = text, False
        return True

    @property
    def dirty(self):
        return self._dump() != self._snapshot

    # ------------------------------------------------------------ acesso
    @property
    def music_volume(self):
        return self.data["audio"]["music_volume"]

    @property
    def sfx_volume(self):
        return self.data["audio"]["sfx_volume"]

    @property
    def video(self):
        return self.data["video"]

    @property
    def controls(self):
        return self.data["controls"]

    @property
    def records(self):
        return self.data["records"]

    def get_record(self, mode):
        """Recorde atual do modo de sobrevivência `mode` (0 se nunca jogado)."""
        return self.data["records"].get(mode, 0)

    def set_record(self, mode, value):
        """Grava `value` como recorde de `mode` SE for maior que o atual (nunca piora um recorde).
        Devolve True quando `value` virou um novo recorde (para a tela de game over anunciar)."""
        if mode not in S.SURVIVAL_GAME_MODES:
            return False
        current = self.get_record(mode)
        is_time = S.RECORD_FIELD.get(mode) == "time"
        value = float(value) if is_time else int(value)
        if value > current:
            self.data["records"][mode] = value
            return True
        return False

    def set_audio(self, music=None, sfx=None):
        if music is not None:
            self.data["audio"]["music_volume"] = _num_in(music, 0, 100, self.music_volume)
        if sfx is not None:
            self.data["audio"]["sfx_volume"] = _num_in(sfx, 0, 100, self.sfx_volume)

    def set_video(self, width, height, fullscreen):
        self.data["video"] = {"width": int(width), "height": int(height), "fullscreen": bool(fullscreen)}

    def set_controls(self, controls):
        self.data["controls"] = copy.deepcopy(controls)
