from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests


class BitcoinRPCError(RuntimeError):
    def __init__(self, message: str, code: int | None = None, details: Any | None = None):
        super().__init__(message)
        self.code = code
        self.details = details


@dataclass(frozen=True)
class RPCConfig:
    scheme: str
    host: str
    port: int
    user: str
    password: str
    wallet: str = ''
    timeout: int = 15


class BitcoinRPC:
    _ids = itertools.count(1)

    def __init__(self, config: RPCConfig):
        self.config = config

    @property
    def base_url(self) -> str:
        return f'{self.config.scheme}://{self.config.host}:{self.config.port}'

    @property
    def wallet_url(self) -> str:
        if not self.config.wallet:
            return self.base_url
        return f'{self.base_url}/wallet/{quote(self.config.wallet)}'

    def call(self, method: str, params: list[Any] | None = None, *, wallet: bool | None = None) -> Any:
        url = self.wallet_url if (wallet if wallet is not None else bool(self.config.wallet)) else self.base_url
        payload = {
            'jsonrpc': '1.0',
            'id': next(self._ids),
            'method': method,
            'params': params or [],
        }
        try:
            response = requests.post(
                url,
                json=payload,
                auth=(self.config.user, self.config.password),
                timeout=self.config.timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise BitcoinRPCError(f'RPC-Verbindung fehlgeschlagen: {exc}') from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise BitcoinRPCError(
                f'Ungültige RPC-Antwort von Bitcoin Core: HTTP {response.status_code}',
                details=response.text[:500],
            ) from exc

        if response.status_code >= 400:
            err = body.get('error') if isinstance(body, dict) else None
            message = err.get('message') if isinstance(err, dict) else response.reason
            code = err.get('code') if isinstance(err, dict) else response.status_code
            raise BitcoinRPCError(f'Bitcoin Core RPC-Fehler: {message}', code=code, details=body)

        if body.get('error'):
            err = body['error']
            raise BitcoinRPCError(f"Bitcoin Core RPC-Fehler: {err.get('message', err)}", code=err.get('code'), details=err)

        return body.get('result')

    def get_blockchain_info(self) -> dict[str, Any]:
        return self.call('getblockchaininfo', wallet=False)

    def get_network_info(self) -> dict[str, Any]:
        return self.call('getnetworkinfo', wallet=False)

    def get_mempool_info(self) -> dict[str, Any]:
        return self.call('getmempoolinfo', wallet=False)

    def get_raw_mempool(self, verbose: bool = False) -> Any:
        return self.call('getrawmempool', [verbose], wallet=False)

    def get_balances(self) -> dict[str, Any]:
        return self.call('getbalances', wallet=True)

    def get_wallet_info(self) -> dict[str, Any]:
        return self.call('getwalletinfo', wallet=True)

    def get_new_address(self, label: str = '', address_type: str | None = None) -> str:
        params: list[Any] = [label]
        if address_type:
            params.append(address_type)
        return self.call('getnewaddress', params, wallet=True)

    def list_received_by_address(self) -> list[dict[str, Any]]:
        # minconf=0, include_empty=true, include_watchonly=true, address_filter omitted
        return self.call('listreceivedbyaddress', [0, True, True], wallet=True)

    def list_unspent(self) -> list[dict[str, Any]]:
        return self.call('listunspent', [0], wallet=True)

    def list_transactions(self, count: int = 50) -> list[dict[str, Any]]:
        return self.call('listtransactions', ['*', count, 0, True], wallet=True)

    def send_to_address(self, address: str, amount: float, fee_rate_sat_vb: float | None = None) -> str:
        # Bitcoin Core's sendtoaddress optional args differ across versions. conf_target/estimate_mode are left null.
        # fee_rate is BTC/kvB in newer Core releases, so convert sat/vB -> BTC/kvB.
        if fee_rate_sat_vb is None:
            return self.call('sendtoaddress', [address, amount], wallet=True)
        btc_per_kvb = fee_rate_sat_vb / 100_000
        return self.call('sendtoaddress', [address, amount, '', '', False, False, None, 'unset', False, btc_per_kvb], wallet=True)

    def get_block_hash(self, height: int) -> str:
        return self.call('getblockhash', [height], wallet=False)

    def get_block(self, block_hash: str, verbosity: int = 2) -> dict[str, Any]:
        return self.call('getblock', [block_hash, verbosity], wallet=False)

    def get_raw_transaction(self, txid: str, verbose: bool = True) -> Any:
        return self.call('getrawtransaction', [txid, verbose], wallet=False)
