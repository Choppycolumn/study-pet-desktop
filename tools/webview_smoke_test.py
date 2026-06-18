#!/usr/bin/env python3
"""Launch the real Qt WebView renderer and verify package/state animation flow."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pet.character import CharacterPackageLoader  # noqa: E402
from pet.renderers.webview_renderer import WebViewRenderer  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=ROOT / "characters" / "default_pet")
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--timeout-ms", type=int, default=20000)
    args = parser.parse_args()

    app = QApplication.instance() or QApplication([])
    package = CharacterPackageLoader(emit_warnings=False).load(args.package)
    renderer = WebViewRenderer()
    renderer.resize(512, 768)
    renderer.show()
    failures: list[str] = []
    states: list[str] = []

    def finish(code: int) -> None:
        renderer.shutdown()
        app.exit(code)

    def inspect_state(state: str, remaining: list[str]) -> None:
        renderer.set_state(state)

        def receive(status: object) -> None:
            try:
                data = json.loads(str(status or "{}"))
            except json.JSONDecodeError:
                data = {}
            active = str(data.get("activeAnimation") or "")
            states.append(active)
            if active != state:
                failures.append(f"state {state!r} resolved to {active!r}")
            if remaining:
                QTimer.singleShot(180, lambda: inspect_state(remaining[0], remaining[1:]))
            else:
                result = {
                    "ready": True,
                    "states": states,
                    "frameCount": data.get("frameCount", 0),
                    "partCount": data.get("partCount", 0),
                    "failures": failures,
                }
                print(json.dumps(result, ensure_ascii=False))
                finish(1 if failures or int(data.get("frameCount", 0)) < 1 else 0)

        renderer.view.page().runJavaScript("JSON.stringify(window.getRendererStatus())", receive)

    def begin_checks() -> None:
        if not args.screenshot:
            inspect_state("idle", ["study", "warning", "angry"])
            return

        def save_canvas(value: object) -> None:
            data_url = str(value or "")
            prefix = "data:image/png;base64,"
            if not data_url.startswith(prefix):
                failures.append("failed to capture Canvas pixels")
            else:
                args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                args.screenshot.write_bytes(base64.b64decode(data_url[len(prefix):]))
            inspect_state("idle", ["study", "warning", "angry"])

        renderer.view.page().runJavaScript(
            "document.getElementById('pet-canvas').toDataURL('image/png')",
            save_canvas,
        )

    def ready(status: object) -> None:
        data = dict(status or {}) if isinstance(status, dict) else {}
        if not data.get("ready") or int(data.get("partCount", 0)) < 1:
            failures.append(f"invalid ready status: {data}")
        QTimer.singleShot(500, begin_checks)

    renderer.renderer_ready.connect(ready)
    renderer.renderer_failed.connect(lambda message: (failures.append(message), finish(1)))
    renderer.set_character(package)
    QTimer.singleShot(max(1000, args.timeout_ms), lambda: (failures.append("timeout"), finish(1)))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
