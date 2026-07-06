import time
from . import db
from .crypto import gen_mnemonic, seed_from_mnemonic, derive_address, sign_p2pkh
from .config import settings


def user_accounts(user_id):
    return db.all('select * from accounts where user_id=? order by id', (user_id,))


def account(account_id, user_id=None):
    if user_id is None:
        return db.one('select * from accounts where id=?', (account_id,))
    return db.one('select * from accounts where id=? and user_id=?', (account_id, user_id))


def first_account(user_id):
    return db.one('select * from accounts where user_id=? order by id limit 1', (user_id,))


def account_by_name(user_id, name):
    return db.one('select * from accounts where user_id=? and name=?', (user_id, name.strip()))


def create_account(user_id, name='Konto 1', mnemonic=None):
    words = (mnemonic or gen_mnemonic()).strip()
    seed = seed_from_mnemonic(words).hex()
    now = int(time.time())
    base = name.strip() or 'Konto'
    final = base
    n = 2
    while account_by_name(user_id, final):
        final = f'{base} {n}'
        n += 1
    aid = db.execute(
        'insert into accounts(user_id,name,mnemonic,seed_hex,xprv,xpub,created_at) values(?,?,?,?,?,?,?)',
        (user_id, final, words, seed, 'lab-xprv', 'lab-xpub', now)
    )
    # Keine Adressen automatisch erzeugen. Der Benutzer erstellt Empfangsadressen bewusst selbst.
    return account(aid, user_id)


def ensure_account(user_id):
    return first_account(user_id) or create_account(user_id, 'Konto 1')


def active_account(user_id, account_id=None):
    if account_id:
        a = account(account_id, user_id)
        if a:
            return a
    return ensure_account(user_id)


def delete_account(user_id, account_id):
    a = account(account_id, user_id)
    if not a:
        raise ValueError('Konto nicht gefunden')
    if len(user_accounts(user_id)) <= 1:
        raise ValueError('Das letzte Konto kann nicht gelöscht werden')
    db.execute('delete from utxos where account_id=? and user_id=?', (account_id, user_id))
    db.execute('delete from addresses where account_id=? and user_id=?', (account_id, user_id))
    db.execute('delete from accounts where id=? and user_id=?', (account_id, user_id))


def restore_wallet(user_id, mnemonic, name='Importiertes Konto'):
    return create_account(user_id, name=name, mnemonic=mnemonic)


def ensure_gap(account_id, branch, count):
    a = account(account_id)
    if not a:
        raise ValueError('Konto nicht gefunden')
    maxrow = db.one('select max(idx) m from addresses where account_id=? and branch=?', (account_id, branch))
    start = (maxrow['m'] + 1) if maxrow and maxrow['m'] is not None else 0
    now = int(time.time())
    for i in range(start, count):
        d = derive_address(a['seed_hex'], branch, i)
        db.execute(
            'insert or ignore into addresses(account_id,user_id,branch,idx,address,pubkey_hex,privkey_hex,wif,label,created_at) values(?,?,?,?,?,?,?,?,?,?)',
            (account_id, a['user_id'], branch, i, d['address'], d['pubkey_hex'], d['privkey_hex'], d['wif'], d['path'], now)
        )


def _insert_derived_address(account_id, branch, idx):
    a = account(account_id)
    if not a:
        raise ValueError('Konto nicht gefunden')
    d = derive_address(a['seed_hex'], branch, idx)
    now = int(time.time())
    db.execute(
        'insert or ignore into addresses(account_id,user_id,branch,idx,address,pubkey_hex,privkey_hex,wif,label,created_at) values(?,?,?,?,?,?,?,?,?,?)',
        (account_id, a['user_id'], branch, idx, d['address'], d['pubkey_hex'], d['privkey_hex'], d['wif'], d['path'], now)
    )
    row = db.one('select * from addresses where account_id=? and branch=? and idx=?', (account_id, branch, idx))
    if row:
        return row
    # Falls dieselbe Adresse global bereits in einem anderen Konto existiert, nächsten Index probieren.
    # Das verhindert UNIQUE(address)-Abstürze bei mehrfach importierten Seeds.
    for j in range(idx + 1, idx + 1000):
        d = derive_address(a['seed_hex'], branch, j)
        db.execute(
            'insert or ignore into addresses(account_id,user_id,branch,idx,address,pubkey_hex,privkey_hex,wif,label,created_at) values(?,?,?,?,?,?,?,?,?,?)',
            (account_id, a['user_id'], branch, j, d['address'], d['pubkey_hex'], d['privkey_hex'], d['wif'], d['path'], now)
        )
        row = db.one('select * from addresses where account_id=? and branch=? and idx=?', (account_id, branch, j))
        if row:
            return row
    raise ValueError('Keine freie Adresse gefunden. Prüfe, ob dasselbe Seed mehrfach importiert wurde.')


def next_receive_address(account_id):
    row = db.one('select max(idx) m from addresses where account_id=? and branch=0', (account_id,))
    idx = 0 if row['m'] is None else row['m'] + 1
    return _insert_derived_address(account_id, 0, idx)


def next_change_address(account_id):
    row = db.one('select max(idx) m from addresses where account_id=? and branch=1', (account_id,))
    idx = 0 if row['m'] is None else row['m'] + 1
    return _insert_derived_address(account_id, 1, idx)


def change_addresses(account_id):
    return db.all('select * from addresses where account_id=? and branch=1 order by idx', (account_id,))


def own_addresses_for_change(account_id):
    return db.all('select * from addresses where account_id=? order by branch,idx', (account_id,))


def receive_addresses(account_id):
    return db.all('select * from addresses where account_id=? and branch=0 order by idx', (account_id,))


def addresses(account_id):
    return db.all('select * from addresses where account_id=? order by branch,idx', (account_id,))


def utxos(account_id):
    return db.all('select * from utxos where account_id=? and spent=0 order by amount_sats desc', (account_id,))


def balance(account_id):
    rows = utxos(account_id)
    total = sum(r['amount_sats'] for r in rows)
    immature = sum(r['amount_sats'] for r in rows if r['coinbase'] and (r['height'] or 0) > 0)
    return {'total_sats': total, 'total': total / 1e8, 'utxo_count': len(rows), 'immature_sats': immature, 'immature': immature / 1e8}


def _utxo_key(u):
    return f"{u['txid']}:{u['vout']}"


def spendable_utxos(account_id):
    rows = []
    for u in utxos(account_id):
        addr = db.one('select * from addresses where account_id=? and address=?', (account_id, u['address']))
        d = dict(u)
        d['key'] = _utxo_key(u)
        d['btc'] = d['amount_sats'] / 100_000_000
        d['path'] = addr['label'] if addr else ''
        d['branch'] = addr['branch'] if addr else None
        d['idx'] = addr['idx'] if addr else None
        rows.append(d)
    return rows


def build_send(account_id, to_addr, amount_btc, fee_sats=None, selected_utxos=None, change_mode='new', change_address=None):
    a = account(account_id)
    if not a:
        raise ValueError('Konto nicht gefunden')
    amount = int(round(float(amount_btc) * 100_000_000))
    fee = int(fee_sats or settings.default_fee_sats)
    selected_set = set(selected_utxos or [])
    available = utxos(account_id)
    if selected_set:
        available = [u for u in available if _utxo_key(u) in selected_set]
    chosen = []
    s = 0
    for u in available:
        addr = db.one('select * from addresses where account_id=? and address=?', (account_id, u['address']))
        if not addr:
            continue
        chosen.append({**dict(u), **{'key': _utxo_key(u), 'privkey_hex': addr['privkey_hex'], 'pubkey_hex': addr['pubkey_hex'], 'path': addr['label']}})
        s += u['amount_sats']
        if not selected_set and s >= amount + fee:
            break
    if not chosen:
        raise ValueError('Keine UTXOs ausgewählt')
    if s < amount + fee:
        raise ValueError(f'Nicht genug Guthaben in der Auswahl. Auswahl: {s} sats, benötigt: {amount + fee} sats')

    outs = [{'address': to_addr, 'amount_sats': amount, 'kind': 'Zahlung'}]
    change = s - amount - fee
    if change > 0:
        if change_mode == 'none':
            # Rest wird absichtlich zur Fee. Nur für Experimente.
            fee += change
            change = 0
        else:
            if change_mode == 'existing':
                if not change_address:
                    raise ValueError('Bitte eine Wechseladresse auswählen')
                own = db.one('select * from addresses where account_id=? and address=?', (account_id, change_address))
                if not own:
                    raise ValueError('Wechseladresse gehört nicht zum aktiven Konto')
                ch_addr = change_address
            else:
                ch = next_change_address(account_id)
                ch_addr = ch['address']
            outs.append({'address': ch_addr, 'amount_sats': change, 'kind': 'Wechselgeld'})
    raw = sign_p2pkh(chosen, outs)
    return raw, chosen, outs, fee
