import os
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()


class Settings:

    bitcoin_rpc_scheme = 'http'
    bitcoin_rpc_timeout = default=15

    bitcoin_rpc_host = os.getenv("RPC_HOST", "127.0.0.1")
    bitcoin_rpc_port = int(os.getenv("RPC_PORT", "8332"))
    bitcoin_rpc_user = os.getenv("RPC_USER", "")
    bitcoin_rpc_password = os.getenv("RPC_PASS", "")
    bitcoin_rpc_wallet = os.getenv("RPC_WALLET", "")

    web_auth_user = os.getenv("WEB_USERNAME", "")
    web_auth_password = os.getenv("WEB_PASSWORD", "")

    app_title = 'Private Bitcoin Core Wallet Frontend'

    secret_key = os.getenv('SECRET_KEY', 'change-me-local-lab-secret')
    database_path = os.getenv('DATABASE_PATH', str('data/wallet_lab.sqlite3'))

    allow_registration = bool(os.getenv('ALLOW_REGISTRATION', True))
    default_user = os.getenv('DEFAULT_USER', 'alice')
    default_password = os.getenv('DEFAULT_PASSWORD', 'alice')

@lru_cache
def get_settings():
    return Settings()
