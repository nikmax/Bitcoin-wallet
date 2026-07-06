import hashlib
import hmac
import os
from fastapi import Request, HTTPException
from starlette.responses import RedirectResponse
from .database import connect, now_iso

def hash_password(password: str, salt_hex: str | None = None) -> str:
    salt = bytes.fromhex(salt_hex) if salt_hex else os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 210_000)
    return f'pbkdf2_sha256${salt.hex()}${dk.hex()}'

def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_hex, digest = stored.split('$', 2)
        if algo != 'pbkdf2_sha256':
            return False
        candidate = hash_password(password, salt_hex).split('$', 2)[2]
        return hmac.compare_digest(candidate, digest)
    except Exception:
        return False

def normalize_username(username: str) -> str:
    return username.strip().lower()

def create_user(username: str, password: str):
    username = normalize_username(username)
    if not username or len(username) < 2:
        raise ValueError('Benutzername ist zu kurz.')
    if len(password) < 3:
        raise ValueError('Passwort ist zu kurz.')
    with connect() as conn:
        created_at = now_iso()
        cur = conn.execute(
            'INSERT INTO users(username, password_hash, created_at) VALUES (?, ?, ?)',
            (username, hash_password(password), created_at)
        )
        return {'id': cur.lastrowid, 'username': username, 'created_at': created_at}

def get_user_by_id(user_id: int):
    with connect() as conn:
        row = conn.execute('SELECT id, username, created_at FROM users WHERE id=?', (user_id,)).fetchone()
        return dict(row) if row else None

def get_user_for_login(username: str):
    username = normalize_username(username)
    with connect() as conn:
        row = conn.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        return dict(row) if row else None

def authenticate(username: str, password: str):
    user = get_user_for_login(username)
    if not user or not verify_password(password, user['password_hash']):
        return None
    return {'id': user['id'], 'username': user['username'], 'created_at': user['created_at']}

def current_user(request: Request):
    user_id = request.session.get('user_id')
    if not user_id:
        return None
    return get_user_by_id(int(user_id))

def require_user(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=303, headers={'Location': '/login'})
    return user

def login_response(request: Request, user: dict):
    request.session['user_id'] = user['id']
    request.session['username'] = user['username']
    return RedirectResponse('/', status_code=303)

def logout_response(request: Request):
    request.session.clear()
    return RedirectResponse('/login', status_code=303)
