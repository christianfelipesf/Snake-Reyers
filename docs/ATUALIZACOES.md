# Atualizacoes

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

A partir da versao `0.1.5`, abra o painel e use **Atualizar sistema**. O painel verifica a versao, baixa o pacote correspondente ao sistema operacional, valida o SHA-256, instala os arquivos e reinicia automaticamente. Para proteger a transmissao, a instalacao so e liberada quando a live esta parada.

Quem estiver em uma versao anterior a `0.1.5` precisa iniciar o Snake Reyers uma vez pelo launcher para receber esse botao. Depois disso, as proximas versoes podem ser instaladas diretamente pelo painel.

A partir da versao `0.1.6`, a instalacao e as atualizacoes criam ou reparam o atalho **Snake Reyers** na Area de Trabalho. No Windows, o atalho inicia o servidor sem exibir a janela do PowerShell.

As musicas e reacoes usam um catalogo independente em `content-manifest.json`. Essa verificacao aparece no painel e nunca instala arquivos enquanto uma live esta iniciando, rodando ou finalizando.
