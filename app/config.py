import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

@dataclass(frozen=True)
class Settings:
    app_title: str = os.getenv('APP_TITLE', 'Private Chain Wallet Lab')
    secret_key: str = os.getenv('SECRET_KEY', 'dev-secret-change-me')
    database_path: str = os.getenv('DATABASE_PATH', 'data/app.db')

    rpc_host: str = os.getenv('RPC_HOST', '127.0.0.1')
    rpc_port: int = int(os.getenv('RPC_PORT', '8332'))
    rpc_user: str = os.getenv('RPC_USER', '')
    rpc_password: str = os.getenv('RPC_PASS', '')
    rpc_timeout: int = int(os.getenv('RPC_TIMEOUT', '15'))

    p2pkh_version: int = int(os.getenv('P2PKH_VERSION', '0'))
    wif_version: int = int(os.getenv('WIF_VERSION', '128'))
    default_fee_sats: int = int(os.getenv('DEFAULT_FEE_SATS', '1000'))

    @property
    def database_file(self) -> Path:
        p = Path(self.database_path)
        if not p.is_absolute():
            p = BASE_DIR / p
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

@lru_cache
def get_settings() -> Settings:
    return Settings()
