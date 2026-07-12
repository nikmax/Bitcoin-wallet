import threading
import time
from . import db
from .rpc import BitcoinRPC
from .config import settings

_lock = threading.Lock()
_job = {'running': False, 'stop': False, 'error': None, 'started_at': None, 'updated_at': None, 'last_height': None, 'batch_size': None, 'done': False}


def _extract_address(vout):
    spk = vout.get('scriptPubKey') or {}
    if spk.get('address'):
        return spk['address']
    addrs = spk.get('addresses') or []
    return addrs[0] if len(addrs) == 1 else None


def indexed_height():
    r = db.one('select height from chain_index_state where id=1')
    return int(r['height']) if r else -1


def index_status():
    rpc = BitcoinRPC()
    tip = int(rpc.call('getblockcount'))
    h = indexed_height()
    with _lock:
        job = dict(_job)
    return {'height': h, 'tip': tip, 'remaining': max(0, tip-h), 'ready': h >= tip, 'job': job}


def _check_reorg(rpc, height):
    if height < 0:
        return height
    row = db.one('select hash from indexed_blocks where height=?', (height,))
    if not row:
        return height
    try:
        current = rpc.call('getblockhash', [height])
    except Exception:
        return height
    if current == row['hash']:
        return height
    # Einfaches Rollback bis zum gemeinsamen Block.
    while height >= 0:
        row = db.one('select hash from indexed_blocks where height=?', (height,))
        if row and rpc.call('getblockhash', [height]) == row['hash']:
            break
        db.execute('delete from chain_outputs where height>=?', (height,))
        db.execute('delete from indexed_blocks where height>=?', (height,))
        height -= 1
    db.execute('update chain_index_state set height=?, updated_at=? where id=1', (height, int(time.time())))
    return height


def index_batch(batch_size=100, start_height=None):
    rpc = BitcoinRPC()
    tip = int(rpc.call('getblockcount'))
    if start_height is not None:
        start = max(0, int(start_height))
        if start == 0:
            db.execute('delete from chain_outputs')
            db.execute('delete from indexed_blocks')
            db.execute('update chain_index_state set height=-1, updated_at=? where id=1', (int(time.time()),))
    else:
        h = _check_reorg(rpc, indexed_height())
        start = h + 1
    if start > tip:
        return {'start': start, 'end': tip, 'tip': tip, 'scanned': 0, 'outputs': 0, 'spent': 0}
    end = min(tip, start + max(1, int(batch_size)) - 1)
    outputs = spent = 0
    with db.conn() as c:
        for height in range(start, end + 1):
            bh = rpc.call('getblockhash', [height])
            block = rpc.call('getblock', [bh, 2])
            btime = block.get('time')
            for tx in block.get('tx', []):
                txid = tx['txid']
                coinbase = 1 if tx.get('vin') and 'coinbase' in tx['vin'][0] else 0
                for vin in tx.get('vin', []):
                    if 'txid' in vin and 'vout' in vin:
                        c.execute('update chain_outputs set spent=1, spent_by=?, spent_height=? where txid=? and vout=?',
                                  (txid, height, vin['txid'], vin['vout']))
                        spent += c.total_changes > 0
                for n, vout in enumerate(tx.get('vout', [])):
                    spk = vout.get('scriptPubKey') or {}
                    script_hex = spk.get('hex') or ''
                    address = _extract_address(vout)
                    sats = int(round(float(vout.get('value', 0)) * 100_000_000))
                    c.execute('''insert or replace into chain_outputs
                      (txid,vout,height,block_hash,block_time,address,script_hex,amount_sats,coinbase,spent,spent_by,spent_height)
                      values(?,?,?,?,?,?,?,?,?,coalesce((select spent from chain_outputs where txid=? and vout=?),0),
                      (select spent_by from chain_outputs where txid=? and vout=?),(select spent_height from chain_outputs where txid=? and vout=?))''',
                      (txid,n,height,bh,btime,address,script_hex,sats,coinbase,txid,n,txid,n,txid,n))
                    outputs += 1
            c.execute('insert or replace into indexed_blocks(height,hash,block_time) values(?,?,?)', (height,bh,btime))
            c.execute('update chain_index_state set height=?, updated_at=? where id=1', (height,int(time.time())))
        c.commit()
    hydrate_all_accounts()
    return {'start': start, 'end': end, 'tip': tip, 'scanned': end-start+1, 'outputs': outputs, 'spent': int(spent)}


def hydrate_account(account_id):
    rows = db.all('select address,user_id from addresses where account_id=?', (account_id,))
    if not rows:
        return {'addresses': 0, 'found': 0}
    found = 0
    for a in rows:
        outs = db.all('select * from chain_outputs where address=?', (a['address'],))
        if outs:
            db.execute('update addresses set used=1, hidden=0 where account_id=? and address=?', (account_id,a['address']))
        for o in outs:
            db.execute('''insert or replace into utxos(txid,vout,account_id,user_id,address,amount_sats,height,block_time,coinbase,spent,spent_by)
                          values(?,?,?,?,?,?,?,?,?,?,?)''',
                       (o['txid'],o['vout'],account_id,a['user_id'],a['address'],o['amount_sats'],o['height'],o['block_time'],o['coinbase'],o['spent'],o['spent_by']))
            found += 1
    return {'addresses': len(rows), 'found': found}


def hydrate_all_accounts():
    for r in db.all('select id from accounts'):
        hydrate_account(r['id'])


def _worker(batch_size, start_height):
    global _job
    try:
        first = True
        while True:
            with _lock:
                if _job['stop']:
                    break
            result = index_batch(batch_size=batch_size, start_height=start_height if first else None)
            first = False
            with _lock:
                _job['last_height'] = result['end']
                _job['updated_at'] = int(time.time())
            if result['end'] >= result['tip'] or result['scanned'] == 0:
                break
    except Exception as e:
        with _lock:
            _job['error'] = str(e)
    finally:
        with _lock:
            _job['running'] = False
            _job['done'] = not _job['stop'] and not _job['error']
            _job['updated_at'] = int(time.time())


def start_indexer(batch_size=100, start_height=None):
    with _lock:
        if _job['running']:
            raise RuntimeError('Indexer läuft bereits')
        _job.update({'running': True,'stop': False,'error': None,'started_at': int(time.time()),'updated_at': int(time.time()),'last_height': None,'batch_size': int(batch_size),'done': False})
    threading.Thread(target=_worker, args=(int(batch_size), start_height), daemon=True).start()


def stop_indexer():
    with _lock:
        _job['stop'] = True
