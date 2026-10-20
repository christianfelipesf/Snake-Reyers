from __future__ import annotations

from fastapi import (
    APIRouter,
    File,
    Form,
    UploadFile,
)
from fastapi.responses import JSONResponse

from cobrinha_server.services import texture_library


router = APIRouter()


@router.get(
    "/api/textures",
    response_class=JSONResponse,
)
def api_textures() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            **texture_library.status(),
        }
    )


@router.post(
    "/api/textures/upload",
    response_class=JSONResponse,
)
async def api_textures_upload(
    texture_type: str = Form(...),
    label: str = Form(""),
    file: UploadFile = File(...),
) -> JSONResponse:
    try:
        data = await file.read()
        result = texture_library.import_texture(
            texture_type=texture_type,
            label=label,
            source_filename=file.filename or "texture.png",
            data=data,
        )
    except ValueError as exc:
        return JSONResponse(
            {
                "ok": False,
                "error": str(exc),
            },
            status_code=400,
        )
    except Exception as exc:
        return JSONResponse(
            {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            },
            status_code=500,
        )

    return JSONResponse(
        {
            "ok": True,
            **result,
        }
    )
