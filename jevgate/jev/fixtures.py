"""Record-and-replay for the Jev Decisions client: responses
saved to fixture files and replayed, so tests and demos run without paid
calls. A fixture is matched by an exact hash of its request body, so replay
only ever answers a request identical to one that was actually recorded.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


def request_key(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


@dataclass
class Fixture:
    request: dict
    status_code: int
    response_body: dict | None = None
    raise_timeout: bool = False


class JevFixtureStore:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._by_key: dict[str, Fixture] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._path.exists():
            return
        for file in sorted(self._path.glob("*.json")):
            data = json.loads(file.read_text(encoding="utf-8"))
            fixture = Fixture(
                request=data["request"],
                status_code=data["status_code"],
                response_body=data.get("response_body"),
                raise_timeout=data.get("raise_timeout", False),
            )
            self._by_key[request_key(fixture.request)] = fixture

    def get(self, payload: dict) -> Fixture | None:
        self._ensure_loaded()
        return self._by_key.get(request_key(payload))

    def save(self, name: str, payload: dict, status_code: int, response_body: dict | None) -> Path:
        self._path.mkdir(parents=True, exist_ok=True)
        out = self._path / f"{name}.json"
        out.write_text(
            json.dumps(
                {"request": payload, "status_code": status_code, "response_body": response_body},
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        # A fixture just written must be answerable immediately in the same process.
        self._by_key[request_key(payload)] = Fixture(
            request=payload, status_code=status_code, response_body=response_body
        )
        return out
