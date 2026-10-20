# Atualizacoes

O launcher verifica atualizacoes antes de iniciar o servidor. A URL do manifesto fica somente no computador do usuario em:

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
