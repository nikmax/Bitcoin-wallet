import hashlib, os, hmac, time
from fastapi import Request
from . import db

def hash_password(pw, salt=None):
    salt=salt or os.urandom(16).hex()
    digest=hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), 120000).hex()
    return f'{salt}${digest}'
def verify_password(pw, stored):
    salt,digest=stored.split('$',1)
    return hmac.compare_digest(hash_password(pw,salt).split('$',1)[1], digest)
def create_user(username, password):
    username=username.strip().lower(); now=int(time.time())
    uid=db.execute('insert into users(username,password_hash,created_at) values(?,?,?)',(username,hash_password(password),now))
    return get_user_by_id(uid)
def get_user_by_id(uid): return db.one('select * from users where id=?',(uid,))
def get_user_by_name(username): return db.one('select * from users where username=?',(username.strip().lower(),))
def current_user(request: Request):
    uid=request.session.get('user_id')
    return get_user_by_id(uid) if uid else None
