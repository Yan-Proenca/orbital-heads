# Changelog — 4 novos modos de sobrevivência

Implementação dos modos **Rockets Sky**, **Ball Rain**, **Mechanic Room** e **Crazy Car**,
seguindo o design doc `ORBITAL_HEADS_PROMPT_ATUALIZADO.md`. Todos os 4 modos reaproveitam os
sistemas existentes (Rocket, BallPod, BouncingSphere, CyberCar, HazardManager, Collision,
Effects, Audio, HUD) através de um `ModeManager` fino por modo — nenhuma física ou colisão
foi duplicada.

## Arquivo novo

- **`game_modes.py`** — `ModeManager` (classe base) + `RocketsSkyMode`, `BallRainMode`,
  `MechanicRoomMode`, `CrazyCarMode`, e a fábrica `make_mode_runner()`.

## Arquivos modificados

### `settings.py`
- `GAME_MODE_ORDER`/`GAME_MODES` ganharam as 4 entradas novas; `SURVIVAL_GAME_MODES` lista
  quais são tocadas por um `ModeManager`.
- Bloco "MODOS DE SOBREVIVÊNCIA": todas as constantes de balanceamento dos 4 modos
  (`ROCKETS_SKY_*`, `BALL_RAIN_*`, `MECHANIC_ROOM_*`, `CRAZY_CAR_*`), incluindo as constantes
  de phasing (`CRAZY_CAR_PLAYER_PHASING_DURATION/DAMAGE_COOLDOWN`) e de spawn do carro
  (`CRAZY_CAR_SPAWN_SIDE/MARGIN`).
- `RECORD_FIELD`: mapeia cada modo ao campo do seu recorde (tempo/round/wave/level).

### `enemy.py` (`CyberCar`)
- `spawn_x()`: centraliza a posição de nascimento (borda direita) — usada agora pelo
  Clássico, 50 Rounds **e** Crazy Car (antes o Clássico nascia no centro da tela).
- Phasing por jogador: `phasing_enabled`, `is_phasing()`, `damage_on_cooldown()`,
  `_start_phasing()` — desativado por padrão (`False`), então Clássico/50 Rounds continuam
  idênticos; só o Crazy Car ativa.
- `stomp()`: o acelerão "`self.speed *= 1.25`" por impacto sobrevivido (comportamento original
  do Clássico) agora só roda quando `phasing_enabled` é `False`. No Crazy Car a velocidade é
  progressão por nível (`CrazyCarMode._speed_for_level`), nunca por impacto dentro do mesmo carro.

### `player.py`
- Pouso sobre o carro: quando `phasing_enabled` e o jogador ainda não está na janela de
  phasing, aplica o impacto (`on_stomp`) e deixa o jogador atravessar, em vez de virar apoio.

### `collisions.py`
- `enemies_vs_players`: pula o dano de contato do carro enquanto `damage_on_cooldown(p)` for
  verdadeiro para aquele jogador.

### `hazards.py`
- `HazardManager.diff_speed`: ganhou um fator opcional `phase_cfg.get("speed_mult", 1.0)`
  (padrão inócuo) — usado pelo Ball Rain/Mechanic Room para acelerar pods/esferas por
  round/ciclo sem tocar em `BallPod`/`BouncingSphere`.
- `BallPod.__init__` (variante "bounce"): ganhou o mesmo tipo de fator opcional
  `phase_cfg.get("bounce_mult", 1.0)` para a "intensidade do quique" do Mechanic Room.

### `wave.py`
- Novo estado `"mode"` em `WaveManager.update()`: roda `hazards.update(dt)` a cada quadro,
  mas **nunca** reage a `hazards.sequence_done` chamando `_finish_round()` por conta própria
  — diferente do estado `"hazard"` do Clássico. Quem decide o que fazer quando uma fase/rodada
  termina é o próprio `ModeManager`. *(Corrige um bug real encontrado durante os testes: sem
  esse estado, o `WaveManager` sobrescrevia o plano do Ball Rain com o do round 1 do Clássico.)*
- `spawn_special` (carro): usa `CyberCar.spawn_x()` em vez de `S.WIDTH / 2`.

### `config.py`
- Bloco `"records"` persistido em `config.json`: um recorde por modo de sobrevivência,
  sanitizado defensivamente (tolerante a `config.json` antigo sem o bloco, ou com valores
  inválidos). `get_record()`/`set_record()` — nunca piora um recorde já salvo.

### `game.py`
- `self.mode_runner` criado em `start_match()` quando `game_mode` é de sobrevivência.
- `Game.update()` chama `mode_runner.update(dt)` antes de `wave.update(dt)`.
- `end_match()` grava o recorde via `mode_runner.on_match_end()`.
- HUD central (`_draw_hud`): mostra `MODO: <nome>` + as linhas do `ModeManager` quando há um
  modo ativo, em vez de "ROUND XX/YY".
- Tela de game over: `_draw_gameover_mode_result()` nova, com painel de altura dinâmica
  (cresce conforme a quantidade de linhas de resultado) para nunca sobrepor a dica de rodapé.
- `on_stomp()`: agora repassa o retorno de `car.stomp()` (antes sempre devolvia `None`).

## Testes novos (`selftest_hazards.py`)

32 testes novos, cobrindo os Testes 1–12 do design doc (seção 23) para os 4 modos:
progressão exata por tempo/round/ciclo/nível, pausa não avança contadores, tetos de
dificuldade respeitados, spawn real de hazards/carro, HUD e tela de resultado no formato
pedido, recordes persistidos e nunca piorados, phasing completo (stomp único, sem apoio, sem
dano durante a janela, individual por jogador, retorno correto após expirar), carro sempre
nascendo na borda direita, e confirmação cruzada de que nenhum modo quebra os demais.

`selftest_settings.py` ganhou 1 teste novo cobrindo o bloco de recordes em `config.json`.

**Resultado final: 52/52 testes em `selftest_hazards.py`, 20/20 em `selftest_settings.py`.**

## Bugs reais encontrados e corrigidos durante a implementação

1. `WaveManager.update()` no estado `"hazard"` chamava `_finish_round()` sozinho sempre que
   `hazards.sequence_done` virava `True`, corrompendo o plano do Ball Rain. Corrigido com o
   novo estado `"mode"`.
2. `CyberCar.stomp()` acelerava a velocidade por impacto sobrevivido, inflando-a sem relação
   com o nível no Crazy Car. Corrigido: esse acelerão só roda quando `phasing_enabled` é falso.
3. `game.on_stomp()` nunca repassava o retorno de `car.stomp()` para fora. Corrigido.
