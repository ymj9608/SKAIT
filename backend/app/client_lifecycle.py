from __future__ import annotations

import time


class ClientConnectionTracker:
    """마지막 SKAIT 브라우저 연결이 사라진 뒤의 유휴 시간을 추적합니다."""

    def __init__(self, idle_seconds: float = 10) -> None:
        self.idle_seconds = idle_seconds
        self._connections: set[str] = set()
        self._disconnected_at: float | None = None
        self._has_connected = False
        self._cleanup_claimed = False

    @property
    def has_connections(self) -> bool:
        return bool(self._connections)

    def connect(self, connection_id: str, *, now: float | None = None) -> None:
        self._connections.add(connection_id)
        self._has_connected = True
        self._disconnected_at = None
        self._cleanup_claimed = False

    def disconnect(self, connection_id: str, *, now: float | None = None) -> None:
        self._connections.discard(connection_id)
        if not self._connections and self._has_connected:
            self._disconnected_at = time.monotonic() if now is None else now

    def claim_idle_cleanup(self, *, now: float | None = None) -> bool:
        if (
            self._connections
            or not self._has_connected
            or self._disconnected_at is None
            or self._cleanup_claimed
        ):
            return False
        current = time.monotonic() if now is None else now
        if current - self._disconnected_at < self.idle_seconds:
            return False
        self._cleanup_claimed = True
        return True
