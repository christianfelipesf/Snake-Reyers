from __future__ import annotations

import time

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.websockets import WebSocketDisconnect

from cobrinha_server.bridge.godot_bridge import (
    godot_bridge,
)
from cobrinha_server.core.settings import (
    PROJECT_DIR,
    application_version,
    ensure_runtime_dirs,
)
from cobrinha_server.routes import build, monitor, panel, session, speech, speech_queue, status, textures
from cobrinha_server.services.speech_dispatcher import (
    start_speech_dispatcher,
)
from cobrinha_server.services.event_decision_worker import (
    start_event_decision_worker,
    stop_event_decision_worker,
)
from cobrinha_server.services.speech_queue import (
    acknowledge_speech_finished,
    active_job,
)
from cobrinha_server.services.tts_worker import (
    start_tts_worker,
    stop_tts_worker,
)
from cobrinha_server.services import (
    content_updates,
    live_watchdog,
    music_runtime,
    top_supporters,
)


def create_app() -> FastAPI:
    ensure_runtime_dirs()

    app = FastAPI(
        title="Snake Reyers Lite",
        version=application_version(),
    )

    app.mount(
        "/static",
        StaticFiles(
            directory=str(
                PROJECT_DIR
                / "src"
                / "cobrinha_server"
                / "static"
            )
        ),
        name="static",
    )

    app.include_router(panel.router)
    app.include_router(status.router)
    app.include_router(build.router)
    app.include_router(session.router)
    app.include_router(monitor.router)
    app.include_router(speech.router)
    app.include_router(speech_queue.router)
    app.include_router(textures.router)

    @app.on_event("startup")
    async def startup_services() -> None:
        start_tts_worker()
        start_speech_dispatcher()
        start_event_decision_worker()
        content_updates.start_startup_sync()

    @app.on_event("shutdown")
    async def shutdown_services() -> None:
        content_updates.stop_background_sync()
        await stop_event_decision_worker()
        stop_tts_worker()

    @app.get("/api/health")
    def health() -> dict[str, object]:
        watchdog = live_watchdog.status()
        components = (
            watchdog.get("components")
            if isinstance(
                watchdog.get("components"),
                dict,
            )
            else {}
        )
        game_component = (
            components.get("game")
            if isinstance(
                components.get("game"),
                dict,
            )
            else {}
        )
        return {
            "ok": True,
            "service": "cobrinha-live-server",
            "time": time.time(),
            "godot": godot_bridge.status(),
            "live_running": bool(
                watchdog.get("active")
            ),
            "game_running": bool(
                game_component.get("running")
            ),
            "watchdog": {
                "status": str(
                    watchdog.get("status")
                    or "idle"
                ),
                "healthy": bool(
                    watchdog.get("healthy")
                ),
                "issues": watchdog.get(
                    "issues",
                    [],
                ),
            },
        }

    @app.get("/api/godot/status")
    def godot_status() -> dict[str, object]:
        return {
            "ok": True,
            **godot_bridge.status(),
        }

    @app.websocket("/ws/godot")
    async def godot_socket(
        socket: WebSocket,
    ) -> None:
        await godot_bridge.connect(socket)

        try:
            await socket.send_json(
                {
                    "type": "server_hello",
                    "protocol": 1,
                }
            )

            await socket.send_json(
                music_runtime.websocket_message()
            )

            await socket.send_json(
                top_supporters.websocket_message()
            )

            while True:
                payload = await socket.receive_json()

                if not isinstance(
                    payload,
                    dict,
                ):
                    continue

                await godot_bridge.remember(
                    payload
                )

                message_type = str(
                    payload.get("type") or ""
                )

                if message_type == "speech_finished":
                    job_id = str(
                        payload.get("job_id")
                        or ""
                    )
                    current_job = active_job()
                    if not job_id:
                        job_id = str(
                            (
                                current_job.get("id")
                                if current_job
                                else ""
                            )
                            or ""
                        )
                    metadata = (
                        current_job.get("metadata")
                        if isinstance(current_job, dict)
                        and isinstance(current_job.get("metadata"), dict)
                        else {}
                    )
                    acknowledge_speech_finished(
                        job_id,
                        sequence_id=str(
                            payload.get("manual_sequence_id")
                            or metadata.get("manual_sequence_id")
                            or ""
                        ),
                        sequence_index=(
                            payload.get("manual_sequence_index")
                            if payload.get("manual_sequence_index") is not None
                            else metadata.get("manual_sequence_index")
                        ),
                    )

                if message_type in {
                    "hello",
                    "heartbeat",
                }:
                    await socket.send_json(
                        {
                            "type": (
                                "hello_ack"
                                if message_type == "hello"
                                else "heartbeat_ack"
                            ),
                            "time": time.time(),
                        }
                    )

        except WebSocketDisconnect:
            pass
        finally:
            await godot_bridge.disconnect(
                socket
            )

    return app


app = create_app()
