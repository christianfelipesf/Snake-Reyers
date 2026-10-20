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

As musicas e reacoes usam um catalogo independente em `content-manifest.json`. Essa verificacao aparece no painel e nunca instala arquivos enquanto uma live esta iniciando, rodando ou finalizando.
