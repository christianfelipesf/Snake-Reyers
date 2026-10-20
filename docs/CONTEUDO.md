# Atualizacoes de conteudo

O Snake Reyers Lite consulta o catalogo oficial em:

```text
https://raw.githubusercontent.com/golgol2/Snake-Reyers/main/content-manifest.json
```

Esse catalogo permite publicar musicas de fundo e recursos de reacao sem gerar novamente o instalador completo. Cada novidade deve ser um ZIP separado em uma Release do GitHub.

## Comportamento no computador do usuario

1. O painel consulta o catalogo ao iniciar.
2. Cada item e comparado com `server/private/content-update-state.json`.
3. Somente versoes novas sao baixadas.
4. O SHA-256 do ZIP precisa coincidir com o catalogo.
5. O ZIP e extraido primeiro em `server/runtime/content-updates`.
6. A troca do diretorio acontece somente com o jogo fechado.
7. Se algo falhar, o conteudo anterior e restaurado.

O usuario pode desativar o download automatico no painel e usar os botoes **Procurar novidades** e **Baixar e instalar**.

## Musica de fundo

Um pacote de musica de fundo deve conter os arquivos de audio na raiz do ZIP. Depois da instalacao, a faixa entra na playlist do jogo.

Exemplo de item no catalogo:

```json
{
  "id": "fundo-noite",
  "title": "Fundo da noite",
  "type": "background_music",
  "version": "1",
  "url": "https://github.com/golgol2/Snake-Reyers/releases/download/content-2026-10/fundo-noite.zip",
  "sha256": "SHA256_DO_ZIP",
  "bytes": 5241500,
  "target": "music/background/fundo-noite"
}
```

## Reacoes

- `gift_reaction`: destino permitido em `content/reactions` para reacoes que o jogo compilado ja saiba executar. As acoes atualmente aceitas sao `gift_cannon` e `heart_me_band`.

Uma animacao 3D completamente nova ainda exige uma versao nova do jogo compilado. O atualizador de conteudo distribui arquivos e configuracoes, mas nao injeta codigo novo no executavel.

## Seguranca

- somente URLs HTTPS sao aceitas em producao;
- todos os pacotes exigem SHA-256;
- caminhos absolutos, `..` e links simbolicos sao recusados;
- cada tipo possui uma pasta de destino permitida;
- downloads e extracoes nao acontecem com o jogo aberto;
- `server/private`, `server/runs` e o runtime instalado nao sao substituidos.
