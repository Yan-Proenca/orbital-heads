# ORBITAL HEADS — migração Tkinter → Pygame

Base de projeto modular para migrar o jogo original (Tkinter `Canvas`) para
**Pygame**, mantendo toda a lógica de jogo (física, armas, boosts, rounds,
chefes) e adicionando: áudio (BGM + SFX), menu de pausa/configurações
navegável, e suporte a controles USB/Bluetooth.

## Estrutura

```
orbital_heads/
├── main.py            # ponto de entrada: init do pygame, janela, loop a 60 FPS com dt
├── settings.py         # TODAS as constantes de jogo (física, armas, boosts, rounds, chefes, áudio, input)
├── game.py             # classe Game: state machine, step(dt), menu de pausa/configurações, draw()
├── player.py           # física do jogador, armas, boosts individuais (porte de Player do main.py)
├── enemy.py            # Enemy base + Drone/Spaceship/FlyingMachine/Boss (ponto de extensão)
├── audio.py            # AudioManager: pygame.mixer para BGM + SFX, com fallback gracioso
├── input_handler.py    # InputManager: unifica teclado + joystick (USB/Bluetooth) por jogador
├── utils.py             # clamp/approach/overlap/mult_clamp — portados sem alteração
├── hazards.py          # (rodada 4) Black Saws, Rockets, Ball Pod, Bouncing Spheres + máquina de fases
├── settings_menu.py    # (rodada 5) menu de configurações: áudio/vídeo/controles
├── display.py          # (rodada 5) janela, resolução, tela cheia, escala letterbox, mouse lógico
├── config.py           # (rodada 5) config.json: volumes, vídeo e atalhos por jogador/dispositivo
├── selftest_settings.py# (rodada 5) testes automáticos headless do menu de configurações
├── selftest_hazards.py # (rodada 4) testes automáticos headless: python selftest_hazards.py
├── requirements.txt
└── assets/
    ├── sfx/             # efeitos sonoros (.ogg/.wav) — ver assets/README.md
    ├── music/           # trilhas (.ogg)
    └── fonts/           # fontes customizadas (opcional; hoje usa SysFont)
```

Cada módulo tem uma responsabilidade única, como no projeto original
(`# uma responsabilidade por classe`), só que agora dividido em **arquivos**
em vez de seções dentro de um único `main.py` de 3700 linhas.

## Como rodar

```bash
pip install -r requirements.txt
python main.py
python main.py --fullscreen
```

Requer Python 3.9+ e Pygame 2.5+. Sem Tkinter, sem dependências de SO.

## 1) Arquitetura modular e loop principal

`main.py` só orquestra: inicializa o pygame, abre a janela, e roda

```python
clock = pygame.time.Clock()
while running:
    dt = min(MAX_DT, clock.tick(FPS) / 1000.0)   # pygame.time.Clock trava em ~60 FPS
    for event in pygame.event.get():
        game.input.handle_event(event)
    game.input.update()
    game.step(dt)          # toda a lógica de jogo (física, colisões, IA, menus)
    game.draw(screen)
    pygame.display.flip()
```

`Game.step(dt)` é a mesma ideia do `step()` original: inteiramente separado
de qualquer chamada gráfica do SO, o que permite (como no `selftest.py`
original) escrever testes automatizados chamando `game.step(1/60)` em loop
sem precisar de uma janela real — basta usar `SDL_VIDEODRIVER=dummy` e
`SDL_AUDIODRIVER=dummy` como variável de ambiente.

`MAX_DT` (em `settings.py`) limita o salto de tempo após um alt-tab ou
travada do SO, exatamente como no original.

## 2) Sistema de áudio

`audio.py` define `AudioManager`, que:

- carrega todos os SFX definidos em `settings.SFX_FILES` como
  `pygame.mixer.Sound` (pré-carregados, baixa latência);
- toca música de fundo via `pygame.mixer.music` (streamada, não ocupa
  memória inteira como os SFX);
- expõe métodos de domínio (`on_shoot`, `on_explosion`, `on_pickup`,
  `on_dash`, `on_player_hit`, ...) para o resto do código não precisar
  conhecer nomes de arquivo — só chamar `game.audio.on_shoot(weapon_key)`;
- tem `cooldown` por som (ex. `explosion_small` com `cooldown=0.03`) para
  não estourar o volume quando 10 explosões acontecem no mesmo quadro;
- **nunca derruba o jogo** se um arquivo de áudio estiver faltando: registra
  um aviso uma vez e segue (`_warn_missing`), o que é essencial durante o
  desenvolvimento, antes de todos os assets finais existirem;
- `toggle_music()` liga/desliga a trilha — é o que o menu de pausa chama.

Exemplo de uso dentro do jogo (já integrado em `player.py`):

```python
self.game.audio.on_shoot(self.weapon)      # dispara o SFX certo por arma
self.game.audio.on_dash()
self.game.audio.on_pickup("boost", good=True)
```

## 3) Menu de pausa e configurações

Em `game.py`, o estado `"paused"` desenha e navega por `PAUSE_ITEMS`:

```python
PAUSE_ITEMS = ("resume", "restart", "music", "settings", "main_menu", "quit")   # rodada 5: "keybinds" virou "settings"
```

- **Resumir**: volta para `"playing"`.
- **Reiniciar Partida**: chama `restart_match()` (reusa `start_match()`).
- **Música**: chama `audio.toggle_music()` e o label mostra
  `"MÚSICA: LIGADA"` / `"MÚSICA: DESLIGADA"` dinamicamente.
- **Configurar Teclas**: entra num submodo (`self.rebinding = (player_idx,
  action)`) que espera o próximo `KEYDOWN` e chama
  `input.rebind_key(player_idx, action, nome_da_tecla)` — dá pra estender
  facilmente para percorrer as 4 ações (`left/right/jump/dash/fire`) de
  cada jogador numa tela dedicada.
- **Menu Inicial**: volta para `"title"`.

Navegação: `↑/↓` move a seleção, `ENTER`/`ESPAÇO` confirma, `ESC` fecha o
menu (volta a jogar) — os mesmos nomes de ação (`global_up`, `global_down`,
`global_return`, `global_escape`) também respondem ao botão **Start/Options**
de qualquer controle conectado (ver `input_handler.InputManager.update`),
então o menu é 100% navegável sem teclado.

## 4) Compatibilidade com controles (USB e Bluetooth)

`pygame.joystick` enumera controles USB e Bluetooth da mesma forma — o SO
e o SDL2 (biblioteca por trás do Pygame) já abstraem o tipo de conexão, não
é preciso tratá-los diferente no código.

`InputManager`:

- escaneia controles no início (`rescan_joysticks()`) e também a cada
  evento `JOYDEVICEADDED`/`JOYDEVICEREMOVED` (conectar um Bluetooth
  depois do jogo já estar aberto também funciona);
- atribui automaticamente o 1º controle encontrado ao Jogador 1 e o 2º ao
  Jogador 2 (`assign_joystick()` permite trocar manualmente depois, útil
  numa tela de configurações);
- lê o eixo horizontal do analógico esquerdo (`get_axis(0)`) **e** o D-pad
  (`get_hat(0)`) e converte em `left`/`right` digitais, com uma zona morta
  (`JOYSTICK_DEADZONE`) para evitar drift;
- mapeia botões para pular/dash/atirar via `settings.GAMEPAD_BUTTONS`
  (índices 0/1/2, que no padrão SDL2 correspondem a A/B/X no Xbox e
  Cross/Circle/Square no PlayStation — ajuste os índices se usar um
  controle fora do padrão);
- gera as MESMAS ações lógicas (`p1_left`, `p2_fire`, ...) que o teclado,
  então teclado e controle podem ser usados **ao mesmo tempo** sem
  conflito — `player.py` não sabe (nem precisa saber) qual dos dois gerou
  a ação.

```python
# settings.py
GAMEPAD_BUTTONS = dict(jump=0, dash=1, fire=2, pause=7)
JOYSTICK_DEADZONE = 0.35
```

Para testar sem um controle físico, o Pygame também aceita controles
virtuais de debug em alguns SOs, mas o mais simples é mesmo conectar um
controle Xbox/PlayStation via USB ou Bluetooth e rodar o jogo — o console
imprime `[input] controle detectado: ...` quando reconhece.

## Status: jogo completo e jogável

Todos os sistemas do `main.py` original foram portados e estão funcionando:

| Sistema | Arquivo | Conteúdo |
|---|---|---|
| Projéteis (tiros, bombas, foguetes, orbes, bombas de jato) | `projectile.py` | `Projectile`, fiel ao original |
| Itens coletáveis (boosts e armas) | `pickup.py` | `Pickup`, com o piscar ao expirar |
| Partículas (explosões, estilhaços, textos, rastro de dash) | `effects.py` | `Effects` + `Debris/Ring/Ghost/Streak/FloatText` |
| Inimigos padrão | `enemy.py` | `Drone`, `Spaceship`, `FlyingMachine`, `MiniShip` |
| Chefes e especiais | `enemy.py` | `Boss`, `Miniboss`, `Mothership`, `FinalBoss`, `CyberCar`, `Jet` |
| Formações e grade espacial | `squad.py` | `Squad`, `SpatialGrid` |
| Progressão dos 10 rounds | `wave.py` | `WaveManager`, idêntico ao original |
| Colisões (tiro×alvo, contato, itens, invasão) | `collisions.py` | `CollisionManager` |
| Menus (mouse + teclado + Xbox/PlayStation) | `menu_input.py` | `MenuInput` — ver seção abaixo |

O jogo roda os 10 rounds de ponta a ponta (testado via simulação automatizada:
Miniboss, Mothership com divisão em mini-naves, CyberCar com mecânica de
pulo/stomp, Jatos + bombas destrutíveis, e o Chefe Final com as três fases
— combate, regeneração e modo frenético).

### O que mudou do original na migração

- **Desenho**: o Canvas do Tkinter mantinha itens persistentes que eram só
  movidos (`canvas.move`); o Pygame não tem isso — cada inimigo/projétil se
  desenha do zero a cada quadro via `draw(surf)`. Os sprites aqui são mais
  simples (formas geométricas em vez dos polígonos detalhados do original),
  mas toda a física, hitboxes, dano, pontuação e padrões de ataque são 1:1.
- **Tremor de tela e flash**: no original isso vinha de `canvas.scan_dragto`;
  aqui é um pequeno deslocamento (`shake_off`) aplicado ao desenhar o mundo
  numa surface à parte antes de colar na tela.
- **Áudio e menus com mouse/controle**: não existiam no original (Tkinter);
  são a parte nova pedida — ver seções 2, 3 e 4 no topo deste README.

## Navegação de menu: teclado, mouse e controle Xbox/PlayStation

Esse era o pedido mais recente: todo menu (**dificuldade** e **pausa/
configurações**) pode ser navegado das três formas ao mesmo tempo, sem
conflito, via `menu_input.MenuInput`:

- **Teclado**: `↑`/`↓` move a seleção, `ENTER`/`ESPAÇO` confirma, `ESC` volta.
- **Mouse**: mover o cursor destaca o item sob ele (hover); clique esquerdo
  confirma. Um cursor customizado (seta) é desenhado nas telas de menu —
  o cursor do sistema operacional fica oculto (`pygame.mouse.set_visible(False)`
  em `main.py`) para não haver dois cursores na tela.
- **Controle Xbox/PlayStation**: o analógico esquerdo (eixo vertical) ou o
  D-pad movem a seleção, com um pequeno atraso no primeiro passo e repetição
  contínua enquanto segurado (`MENU_AXIS_REPEAT_DELAY`/`RATE` em
  `settings.py`); o botão **A** (Xbox) / **Cross** (PlayStation) confirma —
  o mesmo botão usado para pular durante o jogo (`GAMEPAD_BUTTONS["confirm"]`),
  seguindo a convenção usual de jogos de console.

Como cada tela de menu "avisa" o `MenuInput` onde estão seus itens:

```python
# dentro de Game._draw_pause_overlay, por exemplo:
areas = []
for i, item in enumerate(PAUSE_ITEMS):
    rect = txt.get_rect(center=(...))
    areas.append(rect.inflate(260, 18))   # área um pouco maior que o texto
    surf.blit(txt, rect)
self.menu.register_hit_areas(areas)        # mouse agora sabe "onde" cada item está
self.menu.draw_cursor(surf)                 # desenha o cursor por cima de tudo
```

E como a tela de menu *lê* o que o `MenuInput` decidiu, sem se importar se
veio do teclado, do mouse ou do controle:

```python
nav = self.menu.nav_delta()              # -1 / 0 / +1, já com repetição tratada
if nav:
    self.pause_sel = (self.pause_sel + nav) % len(PAUSE_ITEMS)
if self.menu.hovered_index is not None:   # mouse pairando sobre um item
    self.pause_sel = self.menu.hovered_index
if self._confirm_pressed():               # Enter OU clique OU botão A
    self._activate_pause_item(PAUSE_ITEMS[self.pause_sel])
```

Isso significa que dá pra trocar de teclado para mouse para controle no meio
de uma mesma tela de menu sem travar nada — cada fonte de entrada só afeta
`pause_sel`/`menu_sel` no momento em que é usada.

### Tela de configuração de atalhos (remapeamento de teclas)

No menu de pausa, "CONFIGURAR TECLAS" entra numa tela que pede, uma de cada
vez, uma tecla nova para cada ação (`esquerda`, `direita`, `pular`, `dash`,
`atirar`) de cada jogador — 10 passos no total (5 ações × 2 jogadores).
Qualquer tecla do teclado é aceita (não só as pré-cadastradas), via
`pygame.key.key_code()`. `ESC` cancela e volta ao menu de pausa a qualquer
momento.

## Testes automatizados realizados durante o desenvolvimento

Como o projeto não tem display físico neste ambiente, toda a validação foi
feita via simulação headless (`SDL_VIDEODRIVER=dummy`), chamando
`game.step(dt)` em loop e inspecionando o estado resultante — o mesmo
princípio do `selftest.py` do projeto original. Entre os cenários cobertos:
título → dificuldade → partida → movimento físico → pausa → toggle de
música → resumir; uma partida completa dos 10 rounds (incluindo todos os
chefes e encontros especiais) até a vitória; colisão real de tiro matando
inimigo e somando pontos; coleta de pickup trocando a arma do jogador;
navegação de menu por mouse (hover + clique) selecionando uma dificuldade;
navegação por controle Xbox simulado (analógico + botão A); e o fluxo
completo de remapeamento de teclas, incluindo confirmar que a tecla nova
de fato move o jogador depois de remapeada.

## Rodada 3: cidade cyberpunk, 1-4 jogadores, modos de jogo, tela de MVP, controles avançados

### 1) Fundo de cidade cibernética
`background.py` (novo) — `CityBackground`, usada por `Game._draw_background()`.
Camadas de skyline (distante/próxima, parallax leve), janelas de néon
piscando (azul/rosa/roxo/verde), feixes de luz no céu, poluição luminosa no
horizonte e grade de perspectiva no chão (estilo synthwave). **Tudo que não
muda por quadro é pré-renderizado uma única vez** no `__init__` (corpo dos
prédios, céu, grade, feixes) — só o scroll e as janelas que piscam são
recalculados a cada frame, o que é essencial para manter os 60 FPS (ver
seção de performance abaixo).

### 2) Visual de inimigos e pickups
- `enemy.py`: `Enemy.draw()` agora desenha um halo de néon pulsante atrás de
  cada inimigo (`utils.draw_glow_circle` + `utils.pulse`, cor tirada de
  `ENEMY_TYPES[kind]["fx"]`) e um contorno duplo (borda escura de definição +
  linha de néon fina por dentro). Drones, naves, máquinas, carro e chefes
  ganharam luzes/indicadores com glow próprio; barras de vida com cantos
  arredondados e borda da cor do status.
- `pickup.py`: pickups de boost e de arma agora têm um halo de néon que
  cresce e pulsa mais rápido conforme o tempo para coletar acaba (além do
  piscar binário que já existia nos últimos instantes), texto com sombra
  para legibilidade, e a caixa da arma ganhou uma etiqueta "ARMA" para ficar
  clara à distância.

### 3) Opção "SAIR DO JOGO"
Presente tanto no **menu de título** (`TITLE_ITEMS`, abaixo de "INICIAR
JOGO") quanto no **menu de pausa** (`PAUSE_ITEMS`, por último, destacado em
vermelho). Chama `Game.request_quit()`, que seta `game.running = False` —
`main.py` já verificava essa flag a cada quadro, então o loop principal
encerra e o processo fecha normalmente. Navegável por teclado, mouse
(hover + clique) e controle (Xbox/PlayStation/Switch), como qualquer outro
item desses menus.

### 4) Tela de configuração de controles (estilo AAA) — substituída na rodada 5 pela aba CONTROLES do menu de configurações
Reescrita como `Game._draw_keybinds_screen` / `_update_keybinds_menu`,
inspirada no layout de referência (abas no topo, nome da ação à esquerda,
caixa arredondada com a tecla à direita):
- **Abas por jogador**: uma aba "P1"/"P2"/.../"P4" para cada jogador da
  partida atual (até 4), com ícone de teclado ⌨ ou controle 🎮 indicando a
  fonte ativa; trocar com `←`/`→` ou clicando na aba.
- **Linhas de atalho**: `PULAR`, `DASH`, `ATIRAR`, `MOVER ESQUERDA`, `MOVER
  DIREITA` à esquerda; caixa "key cap" arredondada com a tecla atual à
  direita, e ao lado dela o botão de controle equivalente desenhado com a
  cor e o rótulo certos para a família detectada (A/B/X/Y no Xbox, ✕○□▲ no
  PlayStation, etc. — via `gamepad.button_label`/`button_color`).
- **Captura**: clicar/confirmar numa linha entra em modo "pressione uma
  tecla" — aceita tanto uma tecla do teclado quanto um botão de controle
  (apertar um botão associa aquele controle inteiro ao jogador da aba
  atual, liberando-o de qualquer outro jogador que o estivesse usando).
- **Rodapé**: "RESTAURAR PADRÕES" (volta aos binds originais de
  `settings.PLAYER_DEFS` para o jogador da aba atual) e "VOLTAR".

### 5) Modo de jogo, dificuldade e número de jogadores
Fluxo novo entre o título e a partida: `Game.enter_setup()` abre três telas
em sequência (`SETUP_STEPS = ("mode", "difficulty", "players")`), cada uma
navegável por teclado/mouse/controle, com `ENTER` avançando e `ESC`/clique
direito voltando um passo (ou ao título, no primeiro passo):
- **Modo de jogo** (`settings.GAME_MODES`): **Clássico** (10 rounds, termina
  no Chefe Final) ou **Ondas Infinitas** (até 50 rounds — os 10 primeiros
  iguais ao clássico, depois ondas proceduralmente mais difíceis via
  `wave.wave_counts()`, que já crescia e saturava em `MAX_COUNTS`).
- **Dificuldade**: Fácil/Médio/Difícil/Extremo, como antes.
- **Jogadores**: 1 a 4 (`settings.MIN_PLAYERS`/`MAX_PLAYERS`), com uma linha
  de descrição mostrando quantos já têm controle conectado.

`settings.PLAYER_DEFS` ganhou um 3º e um 4º perfil completo (cor, nome,
teclas padrão J/L/I/K/O para P3 e teclado numérico para P4) e `Game.players`
agora é construído dinamicamente para `self.player_count` jogadores, em vez
de sempre 2 — o HUD (`_draw_hud`) se adapta ao layout (cantos para 1-2
jogadores, blocos divididos para 3-4).

### 6) Tela de MVP / resumo de pontuação
Ao terminar a partida (`Game.end_match`), depois da tela de Vitória/Game
Over (que agora pede para confirmar para "ver estatísticas"), entra
`Game._draw_mvp_screen`:
- **MVP da partida**: `Game._determine_mvp()` — maior pontuação, desempate
  por abates — destacado com coroa 👑 e borda dourada.
- **Painel por jogador**: pontuação total, abates totais, e a lista de
  abates por tipo de inimigo (`player.kills_by_type`, já existia e agora é
  exibido), em cards lado a lado que se ajustam de 1 a 4 jogadores.
- Atalhos: `ENTER` reinicia a mesma configuração, `M` volta à tela de
  configuração de partida (escolher outro modo/dificuldade/jogadores), `Q`
  volta ao título.

### 7) `gamepad.py`: suporte avançado a controles
Módulo fornecido integrado como a fonte de verdade para controles em
`input_handler.InputManager`, substituindo o polling direto de
`pygame.joystick` que existia antes:
- Reconhece a **família** do controle pelo nome do dispositivo (Xbox,
  PlayStation, Nintendo Switch, genérico) e escolhe automaticamente o
  mapa de botões certo — inclusive distinguindo DualShock 4 legado
  (DirectInput/Bluetooth, botões em outra ordem) de DualSense/PS5 (HIDAPI
  moderno), que foi uma correção feita durante a integração (ver nota
  abaixo).
- **Conexão dinâmica**: cada controle ganha uma "vaga" ao conectar; ao
  desconectar, a vaga fica reservada (ninguém muda de jogador por engano) e
  um controle do mesmo modelo que volta reocupa a vaga dele.
- **Luz do controle (LED)**: `GamepadManager.set_led()` acende a barra de
  luz do PS4/PS5 com a cor do jogador correspondente ao iniciar a partida
  (`Game._apply_gamepad_leds`) — falha silenciosamente em controles sem
  essa capacidade (Xbox, Switch, DS4 sem o driver certo).
- **Importante sobre o loop de eventos**: o módulo original lia
  `pygame.event.get()` por conta própria; como só pode haver UM consumidor
  da fila de eventos do pygame por quadro, ele foi adaptado para
  `feed_events(events)`, que RECEBE a lista que `main.py` já coletou — nunca
  chama `pygame.event.get()` sozinho. `main.py` repassa essa lista tanto
  para `input.handle_event()` (teclado) quanto para
  `input.feed_gamepad_events()` (controles) no mesmo quadro.

## Desempenho: por que o jogo continua a 60 FPS estáveis

As mudanças visuais desta rodada (fundo animado, halos de néon em todo
inimigo e pickup) adicionam desenho real por quadro, então vale explicar
onde o custo foi gasto com cuidado:

- **`background.py` pré-renderiza tudo que é estático** (céu, corpo dos
  prédios, grade de perspectiva, o "molde" de cada feixe de luz) uma única
  vez em `__init__`, como superfícies prontas; o `draw()` por quadro só faz
  `blit` dessas superfícies com um pequeno deslocamento de scroll, mais o
  desenho direto (sem superfícies temporárias) das poucas janelas acesas
  naquele instante. A primeira versão desta tela recriava uma
  `pygame.Surface` nova por janela/feixe a cada quadro — centenas de
  alocações por segundo — e isso sozinho consumia mais de 60% do tempo de
  quadro; a versão pré-renderizada elimina quase todo esse custo.
- **`utils.draw_glow_circle` cacheia a superfície do halo** por
  `(raio, cor, camadas)` e varia a intensidade (para o "respirar" do pulso)
  com `Surface.set_alpha()`, que é uma operação O(1). A primeira versão
  usava `Surface.copy()` + `BLEND_RGBA_MULT` a cada chamada para aplicar a
  intensidade — com dezenas de inimigos na tela, isso significava milhares
  de cópias de superfície por segundo.
- **`utils.get_font` cacheia `pygame.font.SysFont`** por
  `(nome, tamanho, negrito)`. Criar uma `SysFont` busca a fonte no sistema
  operacional; fazer isso a cada quadro (como o HUD, que roda o tempo todo
  durante a partida, ou a barra de vida de um chefe) é um custo evitável e
  generalizado — todo o código de desenho que roda durante o gameplay
  (`game.py`, `enemy.py`, `player.py`, `pickup.py`) foi migrado para esse
  cache.

Com essas três correções, o pior caso medido do jogo — **4 jogadores, 50
inimigos na tela ao mesmo tempo (round 12), fundo animado e halos de néon
em tudo** — ficou em ~6-7 ms por quadro *neste ambiente de teste* (headless,
driver de vídeo `dummy`, sem qualquer aceleração de hardware), contra um
orçamento de 16.67 ms para 60 FPS: uma folga de ~2.5x. Como esse ambiente é
sempre mais lento que uma tela real com driver de vídeo de verdade, isso dá
margem confortável mesmo em hardware modesto. Antes dessas três correções,
o mesmo cenário consumia ~16 ms por quadro sozinho — ou seja, já estaria
estourando o orçamento de 60 FPS antes mesmo de contar o resto do jogo.

## Testes automatizados desta rodada

Além dos testes já descritos na rodada anterior, esta rodada validou, via
simulação headless (`SDL_VIDEODRIVER=dummy`): o modo Clássico com 1 e 3
jogadores até a vitória no round 10; o modo Ondas Infinitas com 4 jogadores
até a vitória no round 50; o fluxo completo de menus (título → configuração
de partida em 3 passos → jogo → pausa → tela de controles → voltar → fim de
jogo → tela de MVP → nova configuração), misturando teclado, clique de
mouse e um controle Xbox simulado nas mesmas telas; a troca de aba de
jogador e o remapeamento de tecla/botão na tela de configuração de
controles, incluindo "Restaurar Padrões"; a atribuição exclusiva de um
controle a um jogador (que agora libera automaticamente qualquer outro
jogador que o estivesse usando); e a correção da heurística de família
PS4-legado-vs-PS5/DualSense em `gamepad.py`, que inicialmente classificava
incorretamente o DualSense no mapa de botões do DualShock 4 por ambos
conterem "Wireless Controller" no nome reportado pelo sistema.

## Rodada 4: boost de vida, doação de vidas e hazards ambientais

Tudo é configurável em `settings.py` (blocos `LIFE_BOOST`, `LIFE_DONATION`, `HAZARD_*`,
`ROCKET_*`, `BALL_POD_*`, `POD_BALL`, `SPHERE_*`, `BLACK_SAW`); nenhuma classe tem número fixo.

### 1) Boost de vida (`pickup.py`, kind `"life"`)

- Chance **por abate** de qualquer inimigo elegível (`LIFE_BOOST["eligible"]`), a partir do round 4:
  `chance_by_round=((1,0.00),(4,0.03),(6,0.05),(8,0.07),(10,0.09))` — vale a última faixa cujo
  round é ≤ ao atual (rounds 1-3 = 0%, 10+ = 9%).
- Nasce na posição do inimigo, cai até o chão, fica `lifetime` segundos e some. Coleta = `+amount`
  vida, uma única vez (flag `collected`). Quem já está em `max_lives` não coleta (sobra para o aliado).
- Travas de balanceamento (use `999` para desligar): `max_per_round` e `max_active` na tela.
- O sorteio é independente do `roll_drop` comum (não divide o teto de drops de boosts/armas).

### 2) Doação de vidas (`Game.try_donate`, `Player.revive`)

- Ação **`donate_life`** por jogador, integrada ao `InputManager` e à tela de remapeamento:

  | Jogador | Teclado | Controle |
  |---|---|---|
  | P1 | `E` | botão `Y` / ▲ |
  | P2 | `SHIFT DIREITO` | idem |
  | P3 | `U` | idem |
  | P4 | `ENTER` do teclado numérico | idem |

  Nenhuma colide com outra ação ou com teclas globais (há teste automático para isso).
- **Quem pode ser revivido:** jogador **eliminado** (0 vidas, "GAME OVER"). A morte comum (perde 1 vida e
  renasce em `RESPAWN_DELAY`) *não* é alvo: ela já volta sozinha.
- **Regras:** doador ativo, com ≥ `min_donor_lives` (2) vidas; sem aliado eliminado, nada é consumido;
  nunca doa para si; um acionamento = uma tentativa (borda de subida + `cooldown`).
- **Vários mortos:** revive o eliminado **mais recentemente** (`Player.eliminated_at`). Doações no mesmo
  quadro são processadas em sequência, então dois doadores nunca revivem o mesmo aliado.
- O aliado volta com `revive_lives` (1) vida, `invuln` (3 s) de invulnerabilidade e em uma **posição segura**:
  `Game._safe_spawn_x` escolhe o x mais distante de projéteis inimigos, inimigos baixos e hazards.
- Feedback: coração pulsando + "PRECISA DE AJUDA" + tecla do doador sobre o aliado caído, "♥ AJUDA!" no
  painel dele no HUD (some quando ninguém pode doar), corações/anéis/faíscas no renascimento.

### 3) Hazards e fases (`hazards.py`)

| Hazard | Quando existe | Como termina |
|---|---|---|
| **Black Saws** | junto do combate **e** durante todas as fases; saem quando o round fecha | nunca bloqueiam o round |
| **Rockets** | fase própria, depois do combate | temporizador (`duration`) + todos os foguetes resolvidos |
| **Ball Pod** | fase própria, depois do combate | todas as cápsulas **e** mini-esferas destruídas |
| **Bouncing Spheres** | fase própria, depois do combate | todas as esferas destruídas (não termina por tempo) |

Fluxo do round (`WaveManager`): `intro → active (combate) → hazard → clear`. O estado `hazard` só existe se o
round tiver fases; sem fases é `active → clear` direto, como antes. Dentro de `hazard`, cada fase passa por
`warn` (banner, nada nasce) → `run` → (`resolve`, só foguetes) → `cleared` ("HAZARD CLEARED!"); a próxima fase só
começa depois. `WaveManager.update` só roda com o jogo em `playing`, então a **pausa** congela tudo sem código extra.

Travas anti-impasse: objetos com NaN/fora do mundo são descartados; mini-esferas ignoradas estouram após
`POD_BALL["life"]`; cada fase tem teto de `HAZARD_PHASE_TIMEOUT` (limpa o que sobrou) e a espera dos foguetes tem
`HAZARD_RESOLVE_TIMEOUT`.

**Como mudar a distribuição e a ordem por round** — edite `HAZARD_ROUNDS` em `settings.py`:

```python
9: dict(saws=2,                                   # nº de Black Saws durante o combate e as fases
        order=("rockets", "ball_pod", "spheres"), # ordem das fases; omitir = fase não roda
        rockets=dict(duration=13.0, interval=(0.60, 0.95), max_alive=5, mix=(("small", 4), ("medium", 4), ("large", 2))),
        ball_pod=dict(pods=("release", "bounce", "release"), stagger=1.3),
        spheres=dict(mix=(("light", 3), ("heavy", 2)), stagger=0.5)),
```

Só roda uma fase se ela estiver em `order` **e** tiver o bloco de configuração. Ex.: `order=("spheres","rockets")`
inverte a ordem; `order=()` e `saws=0` desligam tudo (padrão do **round 10**, para não interferir nas 3 fases do chefe
final). Quantidades e ritmo crescem `HAZARD_PLAYER_SCALE` (+20%) por jogador extra. No modo infinito (round > 10) o
ciclo `HAZARD_ENDLESS_CYCLE` é reaproveitado com intensidade crescente. Tipos: `ROCKET_TYPES` (tamanho, hp, velocidade,
raio no ar/no chão, pavio), `BALL_POD_TYPES`/`POD_BALL`, `SPHERE_TYPES`/`SPHERE_GRAVITY`, `BLACK_SAW`
(`destructible=True` permite destruí-las a tiros).

Colisões (`collisions.py`): `hazards_vs_arena` (foguete×chão, quique nas paredes/chão/teto), `hazards_vs_players`
(contato; no máximo um golpe por jogador por quadro, e o jogador fica invulnerável após renascer) e tiros×hazards
na mesma passada/grade espacial dos inimigos (`shots_vs_enemies`).

### Testes desta rodada

`python selftest_hazards.py` (headless, ~1 min): chance por round e taxa estatística, ciclo completo do item de
vida, regras de doação (1-4 jogadores, vários mortos, mesmo quadro, posição segura), ordem das fases nos rounds 1-9,
separação combate × fases, física de cada hazard, contato/dano único, pausa, morte de jogador no meio da fase,
modo infinito, 4 dificuldades, boosts globais, reinício no meio de uma fase, partida completa de 10 rounds e desempenho.

## Rodada 5: menu avançado de configurações (áudio, vídeo e controles) + config.json

**Onde abrir:** `CONFIGURAÇÕES` no menu inicial *e* no menu de pausa (no lugar de "CONFIGURAR CONTROLES"). A tela
antiga de atalhos foi absorvida pela aba CONTROLES — não existem dois sistemas. O toggle `MÚSICA: LIGADA/DESLIGADA`
da pausa continua existindo.

**Navegação:** barra lateral `ÁUDIO / VÍDEO · CONTROLES · VOLTAR`. Teclado: `↑/↓` escolhe, `ENTER` ou `→` entra, `←/→`
ajusta sliders/seletores, `ESC` volta (na barra lateral, fecha). Controle: direcional/analógico, `A` confirma, `B` volta.
Mouse: passar o cursor, clicar, **arrastar sliders**, clicar nas setas/segmentos/checkbox; clique direito volta.

### Áudio / Vídeo
- **Volume da música e dos efeitos** (0-100%, passo de 5% no teclado/controle, contínuo no mouse): independentes e
  aplicados na hora ao `AudioManager` existente (`set_music_volume` / `set_sfx_volume`). 0% silencia de verdade
  (efeitos com 0% nem ocupam canal do mixer). Ao arrastar o slider de efeitos toca-se um tiro de amostra.
- **Resolução:** seletor com só o que o monitor suporta (`DisplayManager.available_resolutions`: candidatas de
  `RESOLUTION_CANDIDATES` ∩ tamanho do desktop ∩ `pygame.display.list_modes()` em tela cheia, + modos 16:9 extras).
  Selecionar deixa **PENDENTE**; `APLICAR RESOLUÇÃO` (ou ENTER na linha) aplica. Pedido impossível cai na resolução
  suportada mais próxima, com aviso.
- **Tela cheia:** checkbox que aplica na hora, preservando a resolução escolhida. `F11` (em qualquer tela) e `F`
  (durante a partida) também alternam. A partida **não reinicia**: só a janela é recriada.
- **Como a escala funciona:** o jogo continua desenhando em 1280×720 lógicos e `display.py` escala para a janela,
  com barras pretas se a proporção não for 16:9 (nunca estica; posições relativas idênticas em qualquer resolução).
  O mouse é convertido para coordenadas lógicas. Escalas não inteiras usam `smoothscale` (~6 ms em 1080p); se o FPS
  cair (`perf_level`), o jogo troca para `scale` (~2 ms).

### Controles
- Escolha **jogador** (P1-P4, sempre os 4) × **dispositivo a editar** (`TECLADO · XBOX · PLAYSTATION`). Cada jogador
  tem 3 perfis independentes. A linha `CONTROLE` associa/desassocia um controle ao jogador; ao trocar de jogador o
  dispositivo abre no perfil do controle conectado a ele.
- **Perfis Xbox/PlayStation:** os botões são guardados por *posição* (`a` = baixo, `b` = direita, `x` = esquerda,
  `y` = cima, `lb`, `rb`, `back`) e exibidos com a identidade de cada família (letras coloridas no Xbox; ✕ ○ □ △
  desenhados no PlayStation; `LB/RB` vs `L1/R1`). Em jogo vale o perfil da família do controle conectado
  (`input_handler.pad_device_for`): PlayStation usa o perfil `playstation`; Xbox, Switch e genéricos usam `xbox`.
- **Remapear:** selecione a ação e `ENTER`/clique → `PRESSIONE O NOVO BOTÃO` (ou `A NOVA TECLA`). Cancelar: `ESC`,
  `START`, clique direito, botão CANCELAR ou 10 s sem entrada. A tecla/botão capturado não vaza para o menu nem para o jogo.
- **Regras:** `ESC`, `F` e `F11` (teclado) e `START` (controle) são reservados. Comando já usado por **outra ação do
  mesmo jogador** → pede confirmação e **troca** os dois (ninguém fica sem comando). Tecla usada por **outro jogador**
  → recusada com o aviso de quem a usa (nunca altera os controles dos demais). Movimento no controle é fixo no
  direcional/analógico esquerdo. Itens alterados exibem `PERSONALIZADO`.
- **RESTAURAR PADRÕES:** pede confirmação e restaura só o *jogador + dispositivo* selecionados. Se um padrão de
  teclado colidir com a tecla personalizada de outro jogador, nada é alterado e o aviso diz com quem colide.
- **Desconexão:** o controle some → o jogador volta ao teclado, captura em andamento é cancelada, nada quebra;
  reconectar reassocia.

### Persistência (`config.json`, ao lado de `main.py`; `ORBITAL_CONFIG=/caminho.json` muda o local)
```json
{ "version": 1,
  "audio": {"music_volume": 50, "sfx_volume": 80},
  "video": {"width": 1280, "height": 720, "fullscreen": false},
  "controls": {"1": {"keyboard": {"left": "a", "...": "..."}, "xbox": {"jump": "a", "...": "..."}, "playstation": {"...": "..."}}} }
```
Lido ao iniciar e aplicado (volumes, resolução/tela cheia, atalhos). Ausente → criado com padrões. JSON inválido →
padrões, jogo abre normalmente e o arquivo ruim só é substituído (com cópia `.bak`) quando você mudar algo. Incompleto
ou com valores inválidos → aproveita o que é válido. Só grava quando algo muda (comparação com o último conteúdo) e de
forma atômica. Atalhos adulterados (tecla inexistente/reservada/repetida) são ignorados e valem os padrões.
`python main.py --fullscreen` força tela cheia só naquela execução.

### Testes desta rodada
`python selftest_settings.py` (headless; controles Xbox/PlayStation e mouse são simulados): persistência (criar,
inválido, incompleto, só grava se mudou), volumes independentes/0%/mouse/teclado, resoluções por monitor, escala e
conversão do mouse, aplicar vídeo sem reiniciar a partida, remapeamento de teclado/Xbox/PlayStation, conflitos,
reservadas, restaurar por dispositivo, desconexão, vazamento da tecla capturada, navegação, 1-4 jogadores e `main.py`
real em subprocesso. `python selftest_hazards.py` (rodada 4) continua passando.

## Próximos passos sugeridos (polimento, não funcionalidade)

- Sprites ainda mais detalhados (os atuais são formas geométricas com glow,
  não os polígonos multi-camada do Canvas original).
- Pré-visualização ao vivo do botão de controle durante a captura de bind
  (hoje a captura aceita teclado OU controle, mas a UI não mostra em tempo
  real qual botão está sendo pressionado antes de confirmar).
- Efeito sonoro dedicado para hover do mouse nos itens de menu.
- Persistir a configuração de partida (modo/dificuldade/nº de jogadores)
  e os binds de controle entre execuções do jogo (hoje tudo volta ao
  padrão a cada vez que o processo inicia).
