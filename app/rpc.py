"""Bitcoin Core JSON-RPC client with persistent HTTP connection pooling.

This module intentionally keeps one requests.Session per worker thread.  The
indexer can therefore reuse its TCP connection across thousands of RPC calls
instead of creating a new socket for every getblockhash/getblock request.
"""

from __future__ import annotations

import threading
from typing import Any

import requests
from requests.adapters import HTTPAdapter

from .config import settings


class RPCError(Exception):
    """Raised when Bitcoin Core cannot be reached or returns an RPC error."""


_thread_local = threading.local()


def _thread_session() -> requests.Session:
    """Return one persistent HTTP session for the current thread."""
    session = getattr(_thread_local, "bitcoin_rpc_session", None)
    if session is not None:
        return session

    session = requests.Session()
    session.headers.update(
        {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Connection": "keep-alive",
        }
    )

    # Keep the pool deliberately small. The application talks to one RPC host,
    # and a blocked pool is preferable to exhausting local ephemeral ports.
    adapter = HTTPAdapter(
        pool_connections=2,
        pool_maxsize=4,
        max_retries=0,
        pool_block=True,
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    _thread_local.bitcoin_rpc_session = session
    return session


class BitcoinRPC:
    def __init__(self) -> None:
        self.url = f"http://{settings.rpc_host}:{settings.rpc_port}/"
        self.auth = (settings.rpc_user, settings.rpc_password)
        self.session = _thread_session()

    def call(self, method: str, params: list[Any] | None = None) -> Any:
        payload = {
            "jsonrpc": "1.0",
            "id": "wallet-web",
            "method": method,
            "params": params or [],
        }

        try:
            response = self.session.post(
                self.url,
                json=payload,
                auth=self.auth,
                timeout=settings.rpc_timeout,
            )
        except requests.RequestException as exc:
            raise RPCError(f"Bitcoin Core nicht erreichbar: {exc}") from exc

        if response.status_code != 200:
            raise RPCError(
                f"Bitcoin Core RPC HTTP {response.status_code}: {response.text}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            preview = response.text[:500]
            raise RPCError(
                f"Ungültige JSON-RPC-Antwort von Bitcoin Core: {preview}"
            ) from exc

        error = data.get("error")
        if error:
            raise RPCError(
                f"Bitcoin Core RPC Fehler {error.get('code')}: "
                f"{error.get('message')}"
            )

        return data.get("result")
