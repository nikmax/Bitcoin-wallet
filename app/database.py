import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .config import get_settings

settings = get_settings()

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wallets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    seed_hex TEXT NOT NULL,
    account_path TEXT NOT NULL DEFAULT "m/44'/0'/0'",
    external_index INTEGER NOT NULL DEFAULT 0,
    change_index INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    wallet_id INTEGER,
    label TEXT NOT NULL DEFAULT '',
    private_key_hex TEXT NOT NULL,
    public_key_hex TEXT NOT NULL,
    address TEXT NOT NULL UNIQUE,
    derivation_path TEXT,
    address_type TEXT NOT NULL DEFAULT 'external',
    address_index INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(wallet_id) REFERENCES wallets(id)
);

CREATE TABLE IF NOT EXISTS outgoing_txs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    txid TEXT,
    rawtx TEXT,
    destination TEXT NOT NULL,
    amount_sats INTEGER NOT NULL,
    fee_sats INTEGER NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);
'''

MIGRATIONS = [
    "ALTER TABLE keys ADD COLUMN wallet_id INTEGER",
    "ALTER TABLE keys ADD COLUMN derivation_path TEXT",
    "ALTER TABLE keys ADD COLUMN address_type TEXT NOT NULL DEFAULT 'external'",
    "ALTER TABLE keys ADD COLUMN address_index INTEGER",
]

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def connect() -> sqlite3.Connection:
    db_path = Path(settings.database_file)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn

def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        for sql in MIGRATIONS:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass
