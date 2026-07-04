from __future__ import annotations

import re
from typing import Any

from .config import get_settings
from .rpc import BitcoinRPC, BitcoinRPCError, RPCConfig

_SAFE = re.compile(r'[^a-z0-9_-]+')


def user_wallet_name(username: str) -> str:
    clean = _SAFE.sub('_', username.strip().lower()).strip('_') or 'user'
    return f'lab_{clean}'[:64]


def node_rpc() -> BitcoinRPC:
    s = get_settings()
    return BitcoinRPC(RPCConfig(
        scheme=s.bitcoin_rpc_scheme,
        host=s.bitcoin_rpc_host,
        port=s.bitcoin_rpc_port,
        user=s.bitcoin_rpc_user,
        password=s.bitcoin_rpc_password,
        wallet='',
        timeout=s.bitcoin_rpc_timeout,
    ))


def wallet_rpc(wallet_name: str) -> BitcoinRPC:
    s = get_settings()
    return BitcoinRPC(RPCConfig(
        scheme=s.bitcoin_rpc_scheme,
        host=s.bitcoin_rpc_host,
        port=s.bitcoin_rpc_port,
        user=s.bitcoin_rpc_user,
        password=s.bitcoin_rpc_password,
        wallet=wallet_name,
        timeout=s.bitcoin_rpc_timeout,
    ))


def ensure_wallet_loaded(wallet_name: str) -> dict[str, Any]:
    """Create or load the Bitcoin Core wallet for one app user.

    The app does not keep private keys in SQLite. Bitcoin Core owns keys and signs
    transactions through this named wallet. We prefer a legacy wallet so private
    keys can be exported with dumpprivkey on Core versions that allow it.
    """
    rpc = node_rpc()
    loaded = rpc.call('listwallets', wallet=False)
    if wallet_name in loaded:
        return wallet_rpc(wallet_name).get_wallet_info()

    # If it exists on disk but is not loaded, load it.
    try:
        return rpc.call('loadwallet', [wallet_name], wallet=False)
    except BitcoinRPCError as load_error:
        msg = str(load_error).lower()
        if 'does not exist' not in msg and 'not found' not in msg and load_error.code not in {-18, -35}:
            # Some Core versions say "Wallet already loaded" here; re-check.
            try:
                loaded_after = rpc.call('listwallets', wallet=False)
                if wallet_name in loaded_after:
                    return wallet_rpc(wallet_name).get_wallet_info()
            except BitcoinRPCError:
                pass

    # Create new wallet. Prefer descriptors=false for dumpprivkey compatibility.
    create_attempts = [
        [wallet_name, False, False, '', False, False, True],
        [wallet_name, False, False, '', False, False],
        [wallet_name],
    ]
    last_exc: BitcoinRPCError | None = None
    for params in create_attempts:
        try:
            rpc.call('createwallet', params, wallet=False)
            return wallet_rpc(wallet_name).get_wallet_info()
        except BitcoinRPCError as exc:
            last_exc = exc
            if exc.code not in {-1, -4, -18, -35}:
                break
    if last_exc:
        raise last_exc
    raise BitcoinRPCError('Wallet konnte nicht erstellt oder geladen werden.')


def export_private_key(wallet_name: str, address: str) -> str:
    return wallet_rpc(wallet_name).call('dumpprivkey', [address], wallet=True)
