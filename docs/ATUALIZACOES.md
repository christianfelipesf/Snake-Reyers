# Atualizacoes

## Versao 0.2.0

Esta versao deixa o Snake Reyers mais leve e generico:

- a voz local agora usa Piper, sem dependencias pesadas ou clone de voz;
- o monitor do TikTok funciona direto, com proxy e assinatura opcionais;
- a captura e a transmissao ficam por conta do TikTok LIVE Studio;
- o painel abre e fecha o jogo, sem controlar uma transmissao paralela;
- a cantoria por presente e o processamento de audio pesado foram removidos;
- a musica de fundo continua disponivel com playlist e controle de volume.

As secoes abaixo continuam validas para o atualizador do programa e para o
catalogo de conteudos.

## Versao 0.1.7

O monitor passou a reconhecer limites temporarios de conexao e aguarda o
horario informado pelo servidor antes de tentar novamente. O painel mostra o
estado `LIMITE TEMPORARIO - AGUARDANDO`, e reinicios internos deixam de criar
varias tentativas simultaneas.

Quando esse estado aparecer, mantenha o programa aberto. O monitor retomara
automaticamente; reiniciar o computador ou clicar repetidamente em conectar
nao antecipa a liberacao da cota.

O launcher verifica atualizacoes antes de iniciar o servidor. Por padrao ele usa o manifesto oficial:

```text
https://raw.githubusercontent.com/golgol2/Snake-Reyers/main/update-manifest.json
```

Uma instalacao pode substituir essa URL criando o arquivo:

```text
server/private/update.json
```

Exemplo:

```json
{
  "manifest_url": "https://raw.githubusercontent.com/USUARIO/REPOSITORIO/main/manifest.json"
}
```

O pacote e instalado somente quando a versao e mais nova e o SHA-256 coincide com o manifesto. As pastas `server/private`, `server/runs`, `server/assets` e `server/runtime` sao preservadas.

A partir da versao `0.1.5`, abra o painel e use **Atualizar sistema**. O painel verifica a versao, baixa o pacote correspondente ao sistema operacional, valida o SHA-256, instala os arquivos e reinicia automaticamente. Para evitar interrupcoes, a instalacao so e liberada quando o jogo esta fechado.

Quem estiver em uma versao anterior a `0.1.5` precisa iniciar o Snake Reyers uma vez pelo launcher para receber esse botao. Depois disso, as proximas versoes podem ser instaladas diretamente pelo painel.

A partir da versao `0.1.6`, a instalacao e as atualizacoes criam ou reparam o atalho **Snake Reyers** na Area de Trabalho. No Windows, o atalho inicia o servidor sem exibir a janela do PowerShell.

As musicas de fundo e reacoes usam um catalogo independente em `content-manifest.json`. Essa verificacao aparece no painel e nunca instala arquivos enquanto o jogo esta aberto.
