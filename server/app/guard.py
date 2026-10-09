"""Proteções da API exposta na internet: limite de corpo e bloqueio de IP após falhas de autenticação."""

import math
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Teto de memória do controle por IP: acima disso os registros mais antigos são descartados.
MAX_TRACKED_IPS = 10_000


class BodySizeLimit:
    """Recusa com 413 corpos acima de `limit()` bytes, antes de qualquer leitura pelo FastAPI.

    Confere o Content-Length e também conta os bytes recebidos, para cobrir envio em partes
    (chunked) ou um Content-Length que minta.
    """

    def __init__(self, app: ASGIApp, limit: Callable[[], int]) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        max_bytes = self.limit()
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > max_bytes:
            await self._reject(send)
            return

        received = 0
        rejected = False

        async def counting_receive() -> Message:
            nonlocal received, rejected
            message = await receive()
            if message["type"] == "http.request" and not rejected:
                received += len(message.get("body", b""))
                if received > max_bytes:
                    # Responde já e simula a desconexão: o FastAPI converte exceções lançadas
                    # durante a leitura do corpo em 422, o que esconderia o 413.
                    rejected = True
                    await self._reject(send)
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            if not rejected:
                await send(message)

        await self.app(scope, counting_receive, guarded_send)

    @staticmethod
    async def _reject(send: Send) -> None:
        body = b'{"detail":"Corpo da requisi\xc3\xa7\xc3\xa3o grande demais"}'
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode()),
                                (b"connection", b"close")]})
        await send({"type": "http.response.body", "body": body})


@dataclass
class _Entry:
    fails: int = 0
    blocked_until: float = 0.0


class AuthThrottle:
    """Bloqueia um IP por `block_s` segundos depois de `max_fails` falhas de autenticação seguidas.

    O estado fica só na memória: reiniciar a API libera todos os IPs, o que é aceitável porque o
    objetivo é conter ruído e tentativa de adivinhar token, não guardar histórico.
    """

    def __init__(self, max_fails: int, block_s: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.max_fails = max_fails
        self.block_s = block_s
        self._clock = clock
        self._entries: OrderedDict[str, _Entry] = OrderedDict()

    def retry_after(self, ip: str | None) -> int:
        """Segundos até o IP poder tentar de novo; 0 se não está bloqueado."""
        entry = self._entries.get(ip or "")
        if entry is None:
            return 0
        remaining = entry.blocked_until - self._clock()
        if remaining <= 0:
            if entry.blocked_until:  # bloqueio expirou: começa de novo
                del self._entries[ip or ""]
            return 0
        return math.ceil(remaining)

    def register_failure(self, ip: str | None) -> None:
        key = ip or ""
        entry = self._entries.pop(key, None) or _Entry()
        entry.fails += 1
        if entry.fails >= self.max_fails:
            entry.fails = 0
            entry.blocked_until = self._clock() + self.block_s
        self._entries[key] = entry
        while len(self._entries) > MAX_TRACKED_IPS:
            self._entries.popitem(last=False)

    def register_success(self, ip: str | None) -> None:
        self._entries.pop(ip or "", None)
