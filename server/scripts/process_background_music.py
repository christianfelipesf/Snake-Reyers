from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cobrinha_server.services import music_runtime  # noqa: E402


def main() -> int:
    force = "--force" in sys.argv
    renamed = music_runtime.sanitize_background_filenames()
    sources = music_runtime._source_audio_files()
    processed = []
    skipped = []
    failed = []

    print(
        f"BACKGROUND_MUSIC_BATCH tracks={len(sources)} renamed={len(renamed)}",
        flush=True,
    )

    for index, source in enumerate(
        sources,
        start=1,
    ):
        print(
            f"BACKGROUND_MUSIC_PROCESS {index}/{len(sources)} {source.name}",
            flush=True,
        )
        try:
            item = music_runtime.process_background_track(
                source,
                force=force,
            )
        except Exception as exc:
            failed.append(
                {
                    "source_path": str(source),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            print(
                f"BACKGROUND_MUSIC_FAIL {source.name}: {type(exc).__name__}: {exc}",
                flush=True,
            )
            continue

        if item.get("already_ready"):
            skipped.append(item)
            print(
                f"BACKGROUND_MUSIC_SKIP {source.name}",
                flush=True,
            )
        else:
            processed.append(item)
            print(
                f"BACKGROUND_MUSIC_DONE {source.name}",
                flush=True,
            )

    result = {
        "renamed": renamed,
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
    }
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )

    return 1 if result.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
