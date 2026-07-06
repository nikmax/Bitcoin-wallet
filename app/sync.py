import time
import threading
from . import db
from .rpc import BitcoinRPC
from .config import settings

_job_lock = threading.Lock()
_job = {
    'running': False,
    'started_at': None,
    'updated_at': None,
    'start_height': None,
    'batch_size': None,
    'scope': None,
    'account_id': None,
    'last_result': None,
    'error': None,
    'done': False,
    'stop': False,
}


def addr_map(account_id=None):
    if account_id:
        rows = db.all('select account_id,user_id,address from addresses where account_id=?', (account_id,))
    else:
        rows = db.all('select account_id,user_id,address from addresses')
    return {r['address']: {'user_id': r['user_id'], 'account_id': r['account_id']} for r in rows}


def extract_addresses(vout):
    spk = vout.get('scriptPubKey', {})
    if 'address' in spk:
        return [spk['address']]
    return spk.get('addresses') or []


def reset_sync_to(height=-1, account_id=None):
    if account_id:
        db.execute('delete from utxos where account_id=?', (account_id,))
    else:
        db.execute('delete from utxos')
    db.execute('update sync_state set height=?, updated_at=? where id=1', (int(height), int(time.time())))


def prepare_account_scan(account_id):
    if not account_id:
        return
    from .wallet import ensure_gap
    lookahead = max(1, int(settings.address_gap_limit))
    ensure_gap(account_id, 0, lookahead)
    ensure_gap(account_id, 1, lookahead)


def sync_to_tip(limit=None, start_height=None, account_id=None):
    rpc = BitcoinRPC()
    if account_id is not None:
        prepare_account_scan(account_id)
    tip = rpc.call('getblockcount')
    state = db.one('select height from sync_state where id=1')
    if start_height is not None:
        start = int(start_height)
        if start <= 0:
            reset_sync_to(-1, account_id=account_id)
            start = 0
    else:
        start = max(settings.sync_start_height, (state['height'] if state else -1) + 1)
    if start > tip:
        return {'start': start, 'end': tip, 'tip': tip, 'scanned': 0, 'found': 0, 'spent': 0, 'account_id': account_id, 'note': 'Bereits am Tip'}
    end = tip if limit is None or int(limit) <= 0 else min(tip, start + int(limit) - 1)
    amap = addr_map(account_id=account_id)
    scanned = 0
    found = 0
    spent = 0
    if not amap:
        return {'start': start, 'end': end, 'tip': tip, 'scanned': 0, 'found': 0, 'spent': 0, 'note': 'Keine Adressen vorhanden'}
    for h in range(start, end + 1):
        bh = rpc.call('getblockhash', [h])
        block = rpc.call('getblock', [bh, 2])
        block_time = block.get('time')
        for tx in block.get('tx', []):
            txid = tx['txid']
            coinbase = 1 if tx.get('vin') and 'coinbase' in tx['vin'][0] else 0
            for vin in tx.get('vin', []):
                if 'txid' in vin and 'vout' in vin:
                    cur = db.one('select account_id from utxos where txid=? and vout=?', (vin['txid'], vin['vout']))
                    if cur and (account_id is None or cur['account_id'] == account_id):
                        db.execute('update utxos set spent=1, spent_by=? where txid=? and vout=?', (txid, vin['txid'], vin['vout']))
                        spent += 1
            for n, vout in enumerate(tx.get('vout', [])):
                sats = int(round(float(vout.get('value', 0)) * 100_000_000))
                for address in extract_addresses(vout):
                    hit = amap.get(address)
                    if hit:
                        db.execute(
                            'insert or ignore into utxos(txid,vout,account_id,user_id,address,amount_sats,height,block_time,coinbase,spent) values(?,?,?,?,?,?,?,?,?,0)',
                            (txid, n, hit['account_id'], hit['user_id'], address, sats, h, block_time, coinbase)
                        )
                        db.execute('update addresses set hidden=0, used=1 where account_id=? and address=?', (hit['account_id'], address))
                        found += 1
        if account_id is None:
            db.execute('update sync_state set height=?, updated_at=? where id=1', (h, int(time.time())))
        scanned += 1
    if account_id is not None:
        db.execute('update sync_state set height=max(height,?), updated_at=? where id=1', (end, int(time.time())))
    return {'start': start, 'end': end, 'tip': tip, 'scanned': scanned, 'found': found, 'spent': spent, 'account_id': account_id}


def sync_status():
    rpc = BitcoinRPC()
    tip = rpc.call('getblockcount')
    state = db.one('select * from sync_state where id=1')
    height = state['height'] if state else -1
    return {'height': height, 'tip': tip, 'remaining': max(0, tip - height), 'updated_at': state['updated_at'] if state else None, 'job': background_status()}


def _set_job(**kw):
    with _job_lock:
        _job.update(kw)
        return dict(_job)


def background_status():
    with _job_lock:
        return dict(_job)


def stop_background_sync():
    return _set_job(stop=True)


def _worker(batch_size, start_height, account_id, scope):
    next_start = start_height
    _set_job(running=True, done=False, error=None, stop=False, updated_at=int(time.time()))
    try:
        while True:
            with _job_lock:
                if _job.get('stop'):
                    _job['running'] = False
                    _job['done'] = False
                    _job['updated_at'] = int(time.time())
                    return
            result = sync_to_tip(limit=batch_size, start_height=next_start, account_id=account_id)
            next_start = None
            _set_job(last_result=result, updated_at=int(time.time()))
            if result.get('end', -1) >= result.get('tip', -1) or result.get('scanned', 0) == 0:
                _set_job(running=False, done=True, updated_at=int(time.time()))
                return
            time.sleep(0.15)
    except Exception as e:
        _set_job(running=False, done=False, error=str(e), updated_at=int(time.time()))


def start_background_sync(batch_size=200, start_height=None, account_id=None, scope='account'):
    with _job_lock:
        if _job.get('running'):
            raise RuntimeError('Ein Hintergrund-Scan läuft bereits.')
        _job.update({
            'running': True,
            'started_at': int(time.time()),
            'updated_at': int(time.time()),
            'start_height': start_height,
            'batch_size': int(batch_size),
            'scope': scope,
            'account_id': account_id,
            'last_result': None,
            'error': None,
            'done': False,
            'stop': False,
        })
    t = threading.Thread(target=_worker, args=(int(batch_size), start_height, account_id, scope), daemon=True)
    t.start()
    return background_status()
