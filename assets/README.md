# Assets de áudio

O jogo roda sem nenhum arquivo aqui (o `AudioManager` ignora assets
ausentes e apenas imprime um aviso), mas para ter som completo, adicione:

## assets/sfx/  (efeitos curtos, .ogg ou .wav)
shoot.ogg, shoot_rifle.ogg, shoot_shotgun.ogg, explosion_small.ogg,
explosion_big.ogg, player_hit.ogg, player_death.ogg, pickup_good.ogg,
pickup_bad.ogg, pickup_weapon.ogg, dash.ogg, jump.ogg, menu_move.ogg,
menu_confirm.ogg, round_clear.ogg, boss_warning.ogg, victory.ogg, gameover.ogg

## assets/music/  (trilhas, .ogg recomendado — streamado, não pré-carregado)
title_theme.ogg, gameplay_theme.ogg, boss_theme.ogg, victory_theme.ogg

Os nomes de arquivo exatos (e a chave lógica usada no código, ex.
`audio.play_sfx("shoot")`) estão centralizados em `settings.py`, nos
dicionários `SFX_FILES` e `MUSIC_FILES`. Para trocar um arquivo, basta
editar o valor nesse dicionário — nada mais no código precisa mudar.

Fontes gratuitas compatíveis com uso comercial/livre, caso precise de
assets de placeholder: freesound.org, opengameart.org, kenney.nl/assets.
