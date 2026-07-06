import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

class Settings:
    app_title = os.getenv('APP_TITLE', 'Private Chain Wallet Lab')
    session_secret = os.getenv('SESSION_SECRET', 'dev-secret-change-me')
    database_path = os.getenv('DATABASE_PATH', 'data/app.db')
    rpc_host = os.getenv('RPC_HOST', '127.0.0.1')
    rpc_port = int(os.getenv('RPC_PORT', '8332'))
    rpc_user = os.getenv('RPC_USER', '')
    rpc_password = os.getenv('RPC_PASS', '')
    rpc_timeout = int(os.getenv('RPC_TIMEOUT', '30'))
    sync_start_height = int(os.getenv('SYNC_START_HEIGHT', '0'))
    address_gap_limit = int(os.getenv('ADDRESS_GAP_LIMIT', '20'))
    default_fee_sats = int(os.getenv('DEFAULT_FEE_SATS', '1000'))

settings = Settings()
