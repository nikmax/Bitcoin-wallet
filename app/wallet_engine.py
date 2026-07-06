import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from decimal import Decimal
import base58
from ecdsa import SECP256k1, SigningKey
from .config import get_settings
from .database import connect, now_iso

settings = get_settings()
SAT = 100_000_000
CURVE_ORDER = SECP256k1.order
HARDENED = 0x80000000
XPRV_VERSION = bytes.fromhex('0488ade4')
XPUB_VERSION = bytes.fromhex('0488b21e')

# ---------- low level bitcoin helpers ----------
def sha256(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()

def sha256d(b: bytes) -> bytes:
    return sha256(sha256(b))

def ripemd160(b: bytes) -> bytes:
    h = hashlib.new('ripemd160')
    h.update(b)
    return h.digest()

def hash160(b: bytes) -> bytes:
    return ripemd160(sha256(b))

def btc_to_sats(amount: str | Decimal | float) -> int:
    return int((Decimal(str(amount)) * SAT).to_integral_value())

def sats_to_btc(sats: int) -> Decimal:
    return Decimal(sats) / SAT

def private_key_hex_random() -> str:
    while True:
        n = int.from_bytes(os.urandom(32), 'big')
        if 1 <= n < CURVE_ORDER:
            return n.to_bytes(32, 'big').hex()

def public_key_compressed(priv_hex: str) -> str:
    sk = SigningKey.from_string(bytes.fromhex(priv_hex), curve=SECP256k1)
    vk = sk.verifying_key
    x = vk.pubkey.point.x()
    y = vk.pubkey.point.y()
    prefix = b'\x02' if y % 2 == 0 else b'\x03'
    return (prefix + x.to_bytes(32, 'big')).hex()

def p2pkh_address(pub_hex: str) -> str:
    payload = bytes([settings.p2pkh_version]) + hash160(bytes.fromhex(pub_hex))
    return base58.b58encode_check(payload).decode()

def scriptpubkey_p2pkh(address: str) -> str:
    decoded = base58.b58decode_check(address)
    if len(decoded) != 21:
        raise ValueError('Ungültige P2PKH-Adresse.')
    h160 = decoded[1:]
    return '76a914' + h160.hex() + '88ac'

def wif_from_priv(priv_hex: str, compressed: bool = True) -> str:
    payload = bytes([settings.wif_version]) + bytes.fromhex(priv_hex) + (b'\x01' if compressed else b'')
    return base58.b58encode_check(payload).decode()

# ---------- BIP32-compatible HD wallet helpers ----------
def master_from_seed(seed: bytes) -> tuple[int, bytes]:
    I = hmac.new(b'Bitcoin seed', seed, hashlib.sha512).digest()
    k = int.from_bytes(I[:32], 'big')
    if k == 0 or k >= CURVE_ORDER:
        raise ValueError('Ungültiger HD-Master-Key, bitte neue Wallet erzeugen.')
    return k, I[32:]

def ser32(i: int) -> bytes:
    return i.to_bytes(4, 'big')

def ser256(i: int) -> bytes:
    return i.to_bytes(32, 'big')

def fingerprint(priv_int: int) -> bytes:
    return hash160(bytes.fromhex(public_key_compressed(ser256(priv_int).hex())))[:4]

def ckd_priv(parent_priv: int, parent_chain: bytes, index: int) -> tuple[int, bytes]:
    if index >= HARDENED:
        data = b'\x00' + ser256(parent_priv) + ser32(index)
    else:
        data = bytes.fromhex(public_key_compressed(ser256(parent_priv).hex())) + ser32(index)
    I = hmac.new(parent_chain, data, hashlib.sha512).digest()
    child = (int.from_bytes(I[:32], 'big') + parent_priv) % CURVE_ORDER
    if child == 0:
        raise ValueError('Ungültiger Child-Key, anderer Index nötig.')
    return child, I[32:]

def parse_path(path: str) -> list[int]:
    if path in ('m', ''):
        return []
    if not path.startswith('m/'):
        raise ValueError('Derivation Path muss mit m/ beginnen.')
    out = []
    for part in path[2:].split('/'):
        hardened = part.endswith("'") or part.endswith('h') or part.endswith('H')
        num = int(part[:-1] if hardened else part)
        if num < 0 or num >= HARDENED:
            raise ValueError('Ungültiger Derivation Index.')
        out.append(num + (HARDENED if hardened else 0))
    return out

def derive_priv(seed_hex: str, path: str) -> tuple[int, bytes, bytes, int, int]:
    seed = bytes.fromhex(seed_hex)
    priv, chain = master_from_seed(seed)
    depth = 0
    parent_fp = b'\x00\x00\x00\x00'
    child_num = 0
    for idx in parse_path(path):
        parent_fp = fingerprint(priv)
        priv, chain = ckd_priv(priv, chain, idx)
        child_num = idx
        depth += 1
    return priv, chain, parent_fp, depth, child_num

def serialize_extended(version: bytes, depth: int, parent_fp: bytes, child_num: int, chain: bytes, key_data: bytes) -> str:
    raw = version + bytes([depth]) + parent_fp + ser32(child_num) + chain + key_data
    return base58.b58encode_check(raw).decode()

def xprv_from_seed(seed_hex: str, path: str = 'm') -> str:
    priv, chain, parent_fp, depth, child_num = derive_priv(seed_hex, path)
    return serialize_extended(XPRV_VERSION, depth, parent_fp, child_num, chain, b'\x00' + ser256(priv))

def xpub_from_seed(seed_hex: str, path: str = 'm') -> str:
    priv, chain, parent_fp, depth, child_num = derive_priv(seed_hex, path)
    pub = bytes.fromhex(public_key_compressed(ser256(priv).hex()))
    return serialize_extended(XPUB_VERSION, depth, parent_fp, child_num, chain, pub)

def create_seed_hex() -> str:
    return os.urandom(32).hex()

def seed_backup_phrase(seed_hex: str) -> str:
    # Lab-only backup phrase without external BIP39 wordlist dependency.
    # It is reversible: remove dashes and hex-decode.
    return '-'.join(seed_hex[i:i+4] for i in range(0, len(seed_hex), 4))

# ---------- database-facing wallet functions ----------
def ensure_wallet(user_id: int) -> dict:
    with connect() as conn:
        row = conn.execute('SELECT * FROM wallets WHERE user_id=?', (user_id,)).fetchone()
        if row:
            return dict(row)
        seed = create_seed_hex()
        cur = conn.execute(
            'INSERT INTO wallets(user_id, seed_hex, account_path, external_index, change_index, created_at) VALUES (?, ?, ?, 0, 0, ?)',
            (user_id, seed, "m/44'/0'/0'", now_iso())
        )
        return dict(conn.execute('SELECT * FROM wallets WHERE id=?', (cur.lastrowid,)).fetchone())

def wallet_summary(user_id: int) -> dict:
    w = ensure_wallet(user_id)
    account_path = w['account_path']
    return {
        'id': w['id'],
        'account_path': account_path,
        'external_index': w['external_index'],
        'change_index': w['change_index'],
        'seed_backup_phrase': seed_backup_phrase(w['seed_hex']),
        'account_xprv': xprv_from_seed(w['seed_hex'], account_path),
        'account_xpub': xpub_from_seed(w['seed_hex'], account_path),
    }

def create_hd_key(user_id: int, label: str = '', address_type: str = 'external') -> dict:
    if address_type not in ('external', 'change'):
        raise ValueError('address_type muss external oder change sein.')
    w = ensure_wallet(user_id)
    idx_col = 'external_index' if address_type == 'external' else 'change_index'
    chain = 0 if address_type == 'external' else 1
    index = int(w[idx_col])
    path = f"{w['account_path']}/{chain}/{index}"
    priv_int, _chain, _fp, _depth, _child = derive_priv(w['seed_hex'], path)
    priv = ser256(priv_int).hex()
    pub = public_key_compressed(priv)
    address = p2pkh_address(pub)
    with connect() as conn:
        cur = conn.execute(
            '''INSERT INTO keys(user_id, wallet_id, label, private_key_hex, public_key_hex, address, derivation_path, address_type, address_index, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (user_id, w['id'], label or ('Empfang' if address_type == 'external' else 'Wechselgeld'), priv, pub, address, path, address_type, index, now_iso())
        )
        conn.execute(f'UPDATE wallets SET {idx_col}=? WHERE id=?', (index + 1, w['id']))
        row = conn.execute('SELECT id, user_id, wallet_id, label, public_key_hex, address, derivation_path, address_type, address_index, created_at FROM keys WHERE id=?', (cur.lastrowid,)).fetchone()
        return dict(row)

# backwards-compatible name used by routes
def create_key(user_id: int, label: str = '') -> dict:
    return create_hd_key(user_id, label, 'external')

def create_change_key(user_id: int) -> dict:
    return create_hd_key(user_id, 'Wechselgeld', 'change')

def list_keys(user_id: int, include_private: bool = False) -> list[dict]:
    cols = 'id, user_id, wallet_id, label, public_key_hex, address, derivation_path, address_type, address_index, created_at'
    if include_private:
        cols += ', private_key_hex'
    with connect() as conn:
        rows = conn.execute(f'SELECT {cols} FROM keys WHERE user_id=? ORDER BY address_type ASC, address_index DESC, id DESC', (user_id,)).fetchall()
        return [dict(r) for r in rows]

def get_key_by_address(user_id: int, address: str):
    with connect() as conn:
        row = conn.execute('SELECT * FROM keys WHERE user_id=? AND address=?', (user_id, address)).fetchone()
        return dict(row) if row else None

def all_users_public_addresses() -> list[dict]:
    with connect() as conn:
        rows = conn.execute('''
            SELECT users.username, keys.label, keys.address, keys.derivation_path, keys.address_type, keys.created_at
            FROM keys JOIN users ON users.id = keys.user_id
            WHERE keys.address_type='external'
            ORDER BY users.username, keys.address_index DESC, keys.id DESC
        ''').fetchall()
        return [dict(r) for r in rows]

# ---------- raw transaction helpers, legacy P2PKH only ----------
def little_endian_hex(txid: str) -> str:
    return bytes.fromhex(txid)[::-1].hex()

def varint(n: int) -> str:
    if n < 0xfd:
        return n.to_bytes(1, 'little').hex()
    if n <= 0xffff:
        return 'fd' + n.to_bytes(2, 'little').hex()
    if n <= 0xffffffff:
        return 'fe' + n.to_bytes(4, 'little').hex()
    return 'ff' + n.to_bytes(8, 'little').hex()

def pushdata(hexdata: str) -> str:
    b = bytes.fromhex(hexdata)
    return varint(len(b)) + hexdata

def der_sig(r: int, s: int) -> bytes:
    if s > CURVE_ORDER // 2:
        s = CURVE_ORDER - s
    def enc(x: int) -> bytes:
        b = x.to_bytes((x.bit_length() + 7) // 8 or 1, 'big')
        if b[0] & 0x80:
            b = b'\x00' + b
        return b
    rb, sb = enc(r), enc(s)
    return b'\x30' + bytes([len(rb) + len(sb) + 4]) + b'\x02' + bytes([len(rb)]) + rb + b'\x02' + bytes([len(sb)]) + sb

def tx_base(inputs: list, outputs: list, script_for_index: int | None = None) -> str:
    out = '01000000'
    out += varint(len(inputs))
    for i, inp in enumerate(inputs):
        out += little_endian_hex(inp['txid'])
        out += int(inp['vout']).to_bytes(4, 'little').hex()
        script = inp['scriptPubKey'] if script_for_index == i else ''
        out += varint(len(bytes.fromhex(script))) + script
        out += 'ffffffff'
    out += varint(len(outputs))
    for o in outputs:
        out += int(o['value_sats']).to_bytes(8, 'little').hex()
        script = scriptpubkey_p2pkh(o['address'])
        out += varint(len(bytes.fromhex(script))) + script
    out += '00000000'
    return out

def sign_input(raw_for_sig_hex: str, priv_hex: str) -> str:
    z = sha256d(bytes.fromhex(raw_for_sig_hex) + bytes.fromhex('01000000'))
    sk = SigningKey.from_string(bytes.fromhex(priv_hex), curve=SECP256k1)
    sig = sk.sign_digest_deterministic(z, sigencode=lambda r, s, order: der_sig(r, s)) + b'\x01'
    return sig.hex()

def build_signed_p2pkh_tx(inputs: list, outputs: list) -> str:
    signed_scripts = []
    for i, inp in enumerate(inputs):
        preimage = tx_base(inputs, outputs, script_for_index=i)
        sig_hex = sign_input(preimage, inp['private_key_hex'])
        script_sig = pushdata(sig_hex) + pushdata(inp['public_key_hex'])
        signed_scripts.append(script_sig)

    raw = '01000000' + varint(len(inputs))
    for i, inp in enumerate(inputs):
        raw += little_endian_hex(inp['txid'])
        raw += int(inp['vout']).to_bytes(4, 'little').hex()
        raw += varint(len(bytes.fromhex(signed_scripts[i]))) + signed_scripts[i]
        raw += 'ffffffff'
    raw += varint(len(outputs))
    for o in outputs:
        raw += int(o['value_sats']).to_bytes(8, 'little').hex()
        script = scriptpubkey_p2pkh(o['address'])
        raw += varint(len(bytes.fromhex(script))) + script
    raw += '00000000'
    return raw
