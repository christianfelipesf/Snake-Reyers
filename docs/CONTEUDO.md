# Atualizacoes de conteudo

O Snake Reyers consulta o catalogo oficial em:

```text
https://raw.githubusercontent.com/golgol2/Snake-Reyers/main/content-manifest.json
```

Esse catalogo permite publicar musicas, fundos musicais e recursos de reacao sem gerar novamente o instalador completo. Cada novidade deve ser um ZIP separado em uma Release do GitHub.

## Comportamento no computador do usuario

1. O painel consulta o catalogo ao iniciar.
2. Cada item e comparado com `server/private/content-update-state.json`.
3. Somente versoes novas sao baixadas.
4. O SHA-256 do ZIP precisa coincidir com o catalogo.
5. O ZIP e extraido primeiro em `server/runtime/content-updates`.
6. A troca do diretorio acontece somente com a live parada.
7. Se algo falhar, o conteudo anterior e restaurado.

O usuario pode desativar o download automatico no painel e usar os botoes **Procurar novidades** e **Baixar e instalar**.

## Musica acionada por presente

Uma musica processada deve ser empacotada com todos os arquivos que o `song_runtime` ja utiliza, incluindo o `manifest.json`, os audios e a timeline. Os arquivos ficam na raiz do ZIP.

Exemplo de item no catalogo:

```json
{
  "id": "heart-me-24",
  "title": "Heart Me 24",
  "type": "gift_song",
  "version": "1",
  "url": "https://github.com/golgol2/Snake-Reyers/releases/download/content-2026-10/heart-me-24.zip",
  "sha256": "SHA256_DO_ZIP",
  "bytes": 82415000,
  "target": "singing/processed/FANCLUB/heart-me-24",
  "song_id": "heart-me-24",
  "gift_names": ["Heart Me"],
  "selection": "random",
  "initial_count": 1,
  "repeat_count": 10
}
```

Depois da instalacao, o sistema adiciona a musica as opcoes do presente sem remover as escolhas personalizadas existentes.

## Outros tipos

- `background_music`: destino permitido em `music/background_processed`.
- `gift_reaction`: destino permitido em `content/reactions` para reacoes que o jogo compilado ja saiba executar. As acoes atualmente aceitas sao `gift_cannon` e `heart_me_band`.

Uma animacao 3D completamente nova ainda exige uma versao nova do jogo compilado. O atualizador de conteudo distribui arquivos e configuracoes, mas nao injeta codigo novo no executavel.

## Seguranca

- somente URLs HTTPS sao aceitas em producao;
- todos os pacotes exigem SHA-256;
- caminhos absolutos, `..` e links simbolicos sao recusados;
- cada tipo possui uma pasta de destino permitida;
- downloads e extracoes nao acontecem durante a live;
- `server/private`, `server/runs` e o runtime instalado nao sao substituidos.
