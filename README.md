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
PAUSE_ITEMS = ("resume", "restart", "music", "keybinds", "main_menu")
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

### 4) Tela de configuração de controles (estilo AAA)
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
