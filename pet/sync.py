from __future__ import annotations

import json

from .settings import PetSettings
from .storage import PetStorage

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    requests = None


class SyncClient:
    def __init__(self, settings: PetSettings, storage: PetStorage):
        self.settings = settings
        self.storage = storage

    @property
    def enabled(self) -> bool:
        return requests is not None and bool(self.settings.server_url and self.settings.api_token and self.settings.api_token != "change-me")

    def sync_today(self) -> tuple[bool, str]:
        payload = self.storage.get_report_payload()
        if not self.enabled:
            return False, "同步未配置，请在设置中填写网站地址和 Token。"
        try:
            self._post(payload)
            self._flush_queue()
            return True, "同步成功"
        except Exception as exc:
            self.storage.enqueue_sync(payload, str(exc))
            return False, "同步失败，已进入队列"

    def _post(self, payload: dict) -> None:
        if requests is None:
            raise RuntimeError("requests is not installed")
        response = requests.post(
            f"{self.settings.server_url}/api/study-pet/report",
            headers={"Authorization": f"Bearer {self.settings.api_token}", "Content-Type": "application/json"},
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=8,
        )
        if response.status_code >= 400:
            text = response.text[:300]
            raise RuntimeError(f"server returned {response.status_code}: {text}")

    def _flush_queue(self) -> None:
        for item in self.storage.pending_sync_items():
            try:
                self._post(json.loads(item["payload_json"]))
                self.storage.mark_sync_done(int(item["id"]))
            except Exception as exc:
                self.storage.mark_sync_failed(int(item["id"]), str(exc))
                break
