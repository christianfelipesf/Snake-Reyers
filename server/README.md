# Servidor Snake Reyers Lite

Backend local do jogo Snake Reyers Lite.

Ele fornece o painel web, monitor da live, filas de eventos, geracao de fala, musica e comunicacao WebSocket com a build compilada do jogo.

## Desenvolvimento

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
PYTHONPATH=src .venv/bin/python -m uvicorn cobrinha_server.main:app --host 127.0.0.1 --port 9393
```

O painel fica em `http://127.0.0.1:9393`.

Dados privados sao gravados em `private/` e arquivos temporarios em `runs/`. Essas pastas nunca devem ser enviadas ao GitHub.

O projeto-fonte Godot nao faz parte desta distribuicao. O jogo usa a build compilada correspondente ao sistema operacional.
