import sqlite3
from pathlib import Path
from .config import settings


def db_path():
    p = Path(settings.database_path)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent.parent / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def conn():
    c = sqlite3.connect(db_path())
    c.row_factory = sqlite3.Row
    return c


def _cols(c, table):
    return {r[1] for r in c.execute(f"pragma table_info({table})").fetchall()}


def init_db():
    with conn() as c:
        c.executescript("""
        create table if not exists users(
            id integer primary key,
            username text unique not null,
            password_hash text not null,
            created_at integer not null
        );
        create table if not exists accounts(
            id integer primary key,
            user_id integer not null,
            name text not null,
            mnemonic text not null,
            seed_hex text not null,
            xprv text,
            xpub text,
            created_at integer not null,
            unique(user_id,name)
        );
        create table if not exists addresses(
            id integer primary key,
            account_id integer,
            user_id integer not null,
            branch integer not null,
            idx integer not null,
            address text unique not null,
            pubkey_hex text not null,
            privkey_hex text not null,
            wif text not null,
            label text,
            created_at integer not null
        );
        create table if not exists utxos(
            txid text not null,
            vout integer not null,
            account_id integer,
            user_id integer not null,
            address text not null,
            amount_sats integer not null,
            height integer,
            coinbase integer default 0,
            spent integer default 0,
            spent_by text,
            primary key(txid,vout)
        );
        create table if not exists txs(
            txid text primary key,
            account_id integer,
            user_id integer,
            direction text,
            amount_sats integer,
            raw text,
            created_at integer not null
        );
        create table if not exists sync_state(
            id integer primary key check(id=1),
            height integer not null,
            updated_at integer not null
        );
        insert or ignore into sync_state(id,height,updated_at) values(1, -1, strftime('%s','now'));
        """)
        if 'account_id' not in _cols(c, 'addresses'):
            c.execute('alter table addresses add column account_id integer')
        if 'account_id' not in _cols(c, 'utxos'):
            c.execute('alter table utxos add column account_id integer')
        if 'account_id' not in _cols(c, 'txs'):
            c.execute('alter table txs add column account_id integer')
        tables = {r[0] for r in c.execute("select name from sqlite_master where type='table'").fetchall()}
        if 'wallets' in tables:
            old_wallets = c.execute('select * from wallets').fetchall()
            for w in old_wallets:
                exists = c.execute('select id from accounts where user_id=?', (w['user_id'],)).fetchone()
                if not exists:
                    now = w['created_at'] if 'created_at' in w.keys() else 0
                    aid = c.execute(
                        'insert into accounts(user_id,name,mnemonic,seed_hex,xprv,xpub,created_at) values(?,?,?,?,?,?,?)',
                        (w['user_id'], 'Konto 1', w['mnemonic'], w['seed_hex'], w['xprv'], w['xpub'], now)
                    ).lastrowid
                    c.execute('update addresses set account_id=? where user_id=? and account_id is null', (aid, w['user_id']))
                    c.execute('update utxos set account_id=? where user_id=? and account_id is null', (aid, w['user_id']))
        c.commit()


def one(q, args=()):
    with conn() as c:
        return c.execute(q, args).fetchone()


def all(q, args=()):
    with conn() as c:
        return c.execute(q, args).fetchall()


def execute(q, args=()):
    with conn() as c:
        cur = c.execute(q, args)
        c.commit()
        return cur.lastrowid
