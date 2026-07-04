from __future__ import annotations

import hashlib
import secrets
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import get_settings


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def get_connection() -> sqlite3.Connection:
    settings = get_settings()
    db_path = Path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 200_000)
    return f'pbkdf2_sha256$200000${salt.hex()}${digest.hex()}'


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = stored_hash.split('$', 3)
        if algorithm != 'pbkdf2_sha256':
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, int(iterations))
        return secrets.compare_digest(actual, expected)
    except Exception:
        return False


def init_db() -> None:
    settings = get_settings()
    with get_connection() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            wallet_name TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS user_addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            address TEXT NOT NULL UNIQUE,
            label TEXT NOT NULL DEFAULT '',
            wallet_name TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        ''')
        cols = [r[1] for r in conn.execute('PRAGMA table_info(users)').fetchall()]
        if 'wallet_name' not in cols:
            conn.execute('ALTER TABLE users ADD COLUMN wallet_name TEXT')
        addr_cols = [r[1] for r in conn.execute('PRAGMA table_info(user_addresses)').fetchall()]
        if 'wallet_name' not in addr_cols:
            conn.execute('ALTER TABLE user_addresses ADD COLUMN wallet_name TEXT')

        count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        if count == 0 and settings.default_user and settings.default_password:
            wallet_name = f"lab_{settings.default_user.strip().lower()}"
            conn.execute(
                'INSERT INTO users(username, password_hash, wallet_name, created_at) VALUES (?, ?, ?, ?)',
                (settings.default_user, hash_password(settings.default_password), wallet_name, utcnow()),
            )


def create_user(username: str, password: str) -> dict[str, Any]:
    username = username.strip().lower()
    if not username or len(username) < 3:
        raise ValueError('Benutzername muss mindestens 3 Zeichen haben.')
    if len(password) < 4:
        raise ValueError('Passwort muss mindestens 4 Zeichen haben.')
    with get_connection() as conn:
        try:
            cur = conn.execute(
                'INSERT INTO users(username, password_hash, wallet_name, created_at) VALUES (?, ?, ?, ?)',
                (username, hash_password(password), f'lab_{username}', utcnow()),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError('Benutzername existiert bereits.') from exc
        wallet_name = f"lab_{username}"
        conn.execute('UPDATE users SET wallet_name = ? WHERE id = ?', (wallet_name, cur.lastrowid))
        return get_user_by_id(cur.lastrowid)  # type: ignore[arg-type]


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT id, username, COALESCE(wallet_name, 'lab_' || username) AS wallet_name, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute('SELECT * FROM users WHERE username = ?', (username.strip().lower(),)).fetchone()
        if row and verify_password(password, row['password_hash']):
            return {'id': row['id'], 'username': row['username'], 'wallet_name': row['wallet_name'] or f"lab_{row['username']}", 'created_at': row['created_at']}
    return None


def add_user_address(user_id: int, address: str, label: str = '', wallet_name: str = '') -> None:
    with get_connection() as conn:
        conn.execute(
            'INSERT OR IGNORE INTO user_addresses(user_id, address, label, wallet_name, created_at) VALUES (?, ?, ?, ?, ?)',
            (user_id, address, label.strip(), wallet_name, utcnow()),
        )


def list_user_addresses(user_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            'SELECT id, address, label, wallet_name, created_at FROM user_addresses WHERE user_id = ? ORDER BY id DESC',
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def list_public_users() -> list[dict[str, Any]]:
    with get_connection() as conn:
        users = [dict(row) for row in conn.execute("SELECT id, username, COALESCE(wallet_name, 'lab_' || username) AS wallet_name, created_at FROM users ORDER BY username").fetchall()]
        for user in users:
            rows = conn.execute(
                'SELECT address, label, wallet_name, created_at FROM user_addresses WHERE user_id = ? ORDER BY id DESC LIMIT 10',
                (user['id'],),
            ).fetchall()
            user['addresses'] = [dict(row) for row in rows]
        return users
