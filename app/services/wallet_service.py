from decimal import Decimal
from ..bitcoin_rpc import BitcoinRPC
from ..config import get_settings
from ..database import connect, now_iso
from ..wallet_engine import (
    list_keys, create_key, create_change_key, wallet_summary,
    btc_to_sats, sats_to_btc, build_signed_p2pkh_tx, wif_from_priv
)

settings = get_settings()
rpc = BitcoinRPC()

DUST_LIMIT_SATS = 546

def ensure_first_address(user_id: int):
    wallet_summary(user_id)
    keys = list_keys(user_id)
    if not [k for k in keys if k.get('address_type') == 'external']:
        create_key(user_id, 'Startadresse')

def wallet_addresses(user_id: int):
    ensure_first_address(user_id)
    return list_keys(user_id)

def wallet_meta(user_id: int):
    ensure_first_address(user_id)
    return wallet_summary(user_id)

def confirmed_utxos(user_id: int):
    keys = list_keys(user_id, include_private=True)
    if not keys:
        return []
    by_addr = {k['address']: k for k in keys}
    scans = [f'addr({addr})' for addr in by_addr]
    result = rpc.call('scantxoutset', ['start', scans])
    utxos = []
    for u in result.get('unspents', []):
        addr = u.get('address') or ''
        key = by_addr.get(addr)
        if not key:
            for a, k in by_addr.items():
                if a in str(u):
                    key = k
                    addr = a
                    break
        if not key:
            continue
        amount_sats = btc_to_sats(str(u['amount']))
        utxos.append({
            'txid': u['txid'],
            'vout': u['vout'],
            'address': addr,
            'label': key.get('label'),
            'derivation_path': key.get('derivation_path'),
            'address_type': key.get('address_type'),
            'amount': u['amount'],
            'amount_sats': amount_sats,
            'amount_btc': sats_to_btc(amount_sats),
            'height': u.get('height'),
            'scriptPubKey': u['scriptPubKey'],
            'private_key_hex': key['private_key_hex'],
            'public_key_hex': key['public_key_hex'],
            'wif': wif_from_priv(key['private_key_hex']),
        })
    return sorted(utxos, key=lambda x: (x.get('height') or 0, x['txid'], x['vout']))

def balance(user_id: int):
    try:
        utxos = confirmed_utxos(user_id)
        total = sum(u['amount_sats'] for u in utxos)
        return {'confirmed_sats': total, 'confirmed_btc': sats_to_btc(total), 'utxos': utxos, 'error': None}
    except Exception as e:
        return {'confirmed_sats': 0, 'confirmed_btc': Decimal(0), 'utxos': [], 'error': str(e)}

def select_coins(utxos: list[dict], target_sats: int):
    selected = []
    total = 0
    # Smallest-first is simple and understandable for a lab wallet.
    for u in sorted(utxos, key=lambda x: x['amount_sats']):
        selected.append(u)
        total += u['amount_sats']
        if total >= target_sats:
            return selected, total
    raise ValueError('Nicht genug bestätigte UTXOs für Betrag + Fee.')

def build_payment_preview(user_id: int, destination: str, amount_btc: str, fee_sats: int | None = None, change_address_hint: str | None = None):
    fee_sats = int(fee_sats or settings.default_fee_sats)
    amount_sats = btc_to_sats(amount_btc)
    if amount_sats <= 0:
        raise ValueError('Betrag muss größer als 0 sein.')
    if fee_sats < 0:
        raise ValueError('Fee darf nicht negativ sein.')
    # Validate destination by trying to create a P2PKH script. v0.3 supports only Legacy P2PKH outputs.
    from ..wallet_engine import scriptpubkey_p2pkh
    scriptpubkey_p2pkh(destination)

    selected, total = select_coins(confirmed_utxos(user_id), amount_sats + fee_sats)
    change_sats = total - amount_sats - fee_sats
    change_address = None
    outputs = [{'address': destination, 'value_sats': amount_sats, 'kind': 'payment'}]
    if change_sats > DUST_LIMIT_SATS:
        if change_address_hint:
            owned = [k for k in list_keys(user_id) if k['address'] == change_address_hint and k.get('address_type') == 'change']
            if not owned:
                raise ValueError('Change-Adresse gehört nicht zu dieser Wallet.')
            change_address = change_address_hint
        else:
            change_key = create_change_key(user_id)
            change_address = change_key['address']
        outputs.append({'address': change_address, 'value_sats': change_sats, 'kind': 'change'})
    else:
        # If change would be dust, add it to fee for a standard transaction.
        fee_sats += change_sats
        change_sats = 0
    rawtx = build_signed_p2pkh_tx(selected, outputs)
    return {
        'destination': destination,
        'amount_sats': amount_sats,
        'amount_btc': sats_to_btc(amount_sats),
        'fee_sats': fee_sats,
        'fee_btc': sats_to_btc(fee_sats),
        'input_sats': total,
        'input_btc': sats_to_btc(total),
        'change_sats': change_sats,
        'change_btc': sats_to_btc(change_sats),
        'change_address': change_address,
        'inputs': selected,
        'outputs': outputs,
        'rawtx': rawtx,
    }

def broadcast_payment(user_id: int, destination: str, amount_btc: str, fee_sats: int | None = None, change_address_hint: str | None = None):
    preview = build_payment_preview(user_id, destination, amount_btc, fee_sats, change_address_hint)
    try:
        txid = rpc.call('sendrawtransaction', [preview['rawtx']])
        status = 'broadcasted'
        error = None
    except Exception as e:
        txid = None
        status = 'error'
        error = str(e)
    with connect() as conn:
        conn.execute(
            'INSERT INTO outgoing_txs(user_id, txid, rawtx, destination, amount_sats, fee_sats, status, error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (user_id, txid, preview['rawtx'], destination, preview['amount_sats'], preview['fee_sats'], status, error, now_iso())
        )
    if error:
        raise RuntimeError(error)
    return txid, preview

def outgoing_history(user_id: int):
    with connect() as conn:
        rows = conn.execute('SELECT * FROM outgoing_txs WHERE user_id=? ORDER BY id DESC LIMIT 20', (user_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d['amount_btc'] = sats_to_btc(d['amount_sats'])
            d['fee_btc'] = sats_to_btc(d['fee_sats'])
            out.append(d)
        return out
