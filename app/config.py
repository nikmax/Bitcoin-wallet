import os
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()

print("RPC_HOST =", os.getenv("RPC_HOST"))


class Settings:

    #model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

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


@lru_cache
def get_settings():
    return Settings()
