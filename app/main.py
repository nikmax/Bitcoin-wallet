from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path
import io
import qrcode
from datetime import datetime
from .config import settings
from . import db
from .auth import create_user, get_user_by_name, verify_password, current_user
from .wallet import (
    ensure_account, active_account, user_accounts, create_account, delete_account,
    restore_wallet, next_receive_address, addresses, hidden_address_count, balance, utxos, build_send, spendable_utxos, change_addresses, own_addresses_for_change
)
from .sync import sync_to_tip, sync_status, start_background_sync, background_status, stop_background_sync
from .rpc import BitcoinRPC

BASE = Path(__file__).resolve().parent
app = FastAPI(title=settings.app_title)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
app.mount('/static', StaticFiles(directory=BASE / 'static'), name='static')
templates = Jinja2Templates(directory=BASE / 'templates')

def fmt_ts(value):
    if not value:
        return 'unbekannt'
    try:
        return datetime.fromtimestamp(int(value)).strftime('%Y-%m-%d')
    except Exception:
        return 'unbekannt'

templates.env.filters['date'] = fmt_ts


@app.on_event('startup')
def startup():
    db.init_db()


@app.get('/qr.png')
def qr_png(data: str):
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return Response(content=buf.getvalue(), media_type='image/png')


def get_active_account(request, user):
    aid = request.session.get('account_id')
    a = active_account(user['id'], aid)
    request.session['account_id'] = a['id']
    return a


def render(request, template, context=None, status_code=200):
    user = current_user(request)
    ctx = {'request': request, 'settings': settings, 'user': user, 'accounts': [], 'account': None}
    if user:
        ctx['accounts'] = user_accounts(user['id'])
        ctx['account'] = get_active_account(request, user)
    if context:
        ctx.update(context)
    return templates.TemplateResponse(request, template, ctx, status_code=status_code)


def require_user(request):
    u = current_user(request)
    if not u:
        return None
    ensure_account(u['id'])
    return u


@app.get('/login')
def login_page(request: Request):
    return render(request, 'login.html', {'error': None})


@app.post('/login')
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    u = get_user_by_name(username)
    if not u or not verify_password(password, u['password_hash']):
        return render(request, 'login.html', {'error': 'Login fehlgeschlagen'}, 401)
    request.session['user_id'] = u['id']
    a = ensure_account(u['id'])
    request.session['account_id'] = a['id']
    return RedirectResponse('/', 303)


@app.get('/logout')
def logout(request: Request):
    request.session.clear()
    return RedirectResponse('/login', 303)


@app.get('/register')
def register_page(request: Request):
    return render(request, 'register.html', {'error': None})


@app.post('/register')
def register(request: Request, username: str = Form(...), password: str = Form(...)):
    try:
        u = create_user(username, password)
        a = ensure_account(u['id'])
        request.session['user_id'] = u['id']
        request.session['account_id'] = a['id']
        return RedirectResponse('/', 303)
    except Exception as e:
        return render(request, 'register.html', {'error': str(e)}, 400)


@app.post('/accounts/select')
def select_account(request: Request, account_id: int = Form(...)):
    u = require_user(request)
    if not u:
        return RedirectResponse('/login', 303)
    a = active_account(u['id'], account_id)
    request.session['account_id'] = a['id']
    return RedirectResponse('/wallet', 303)


@app.post('/accounts/create')
def create_account_route(request: Request, name: str = Form('Neues Konto')):
    u = require_user(request)
    if not u:
        return RedirectResponse('/login', 303)
    a = create_account(u['id'], name)
    request.session['account_id'] = a['id']
    return RedirectResponse('/wallet', 303)


@app.post('/accounts/delete')
def delete_account_route(request: Request, account_id: int = Form(...)):
    u = require_user(request)
    if not u:
        return RedirectResponse('/login', 303)
    try:
        delete_account(u['id'], account_id)
        a = ensure_account(u['id'])
        request.session['account_id'] = a['id']
    except Exception:
        pass
    return RedirectResponse('/wallet', 303)


@app.get('/')
def dashboard(request: Request):
    u = require_user(request)
    if not u:
        return RedirectResponse('/login', 303)
    a = get_active_account(request, u)
    err = None
    chain = {}
    status = {}
    try:
        rpc = BitcoinRPC()
        chain = rpc.call('getblockchaininfo')
        status = sync_status()
    except Exception as e:
        err = str(e)
    return render(request, 'dashboard.html', {'chain': chain, 'balances': balance(a['id']), 'sync': status, 'error': err})


@app.get('/wallet')
def wallet_page(request: Request):
    u = require_user(request)
    if not u:
        return RedirectResponse('/login', 303)
    a = get_active_account(request, u)
    return render(request, 'wallet.html', {'addresses': addresses(a['id']), 'hidden_addresses': hidden_address_count(a['id']), 'utxos': utxos(a['id']), 'balances': balance(a['id'])})


@app.post('/wallet/address')
def make_addr(request: Request):
    u = require_user(request)
    if not u:
        return RedirectResponse('/login', 303)
    a = get_active_account(request, u)
    next_receive_address(a['id'])
    return RedirectResponse('/wallet', 303)


@app.get('/backup')
def backup_page(request: Request):
    u = require_user(request)
    if not u:
        return RedirectResponse('/login', 303)
    a = get_active_account(request, u)
    return render(request, 'backup.html', {'error': None, 'import_result': None, 'account': a})


@app.post('/backup/import')
def import_seed(
    request: Request,
    mnemonic: str = Form(...),
    name: str = Form('Importiertes Konto'),
    scan_from: int = Form(0),
    scan_limit: int = Form(1000),
    scan_now: str = Form(None),
):
    u = require_user(request)
    if not u:
        return RedirectResponse('/login', 303)
    try:
        a = restore_wallet(u['id'], mnemonic, name=name)
        request.session['account_id'] = a['id']
        result = None
        if scan_now:
            result = sync_to_tip(limit=scan_limit, start_height=scan_from, account_id=a['id'])
        return render(request, 'backup.html', {'error': None, 'import_result': result, 'account': a})
    except Exception as e:
        a = get_active_account(request, u)
        return render(request, 'backup.html', {'error': str(e), 'import_result': None, 'account': a}, 400)


@app.get('/sync')
def sync_page(request: Request):
    u = require_user(request)
    if not u:
        return RedirectResponse('/login', 303)
    try:
        status = sync_status()
        err = None
    except Exception as e:
        status = {}
        err = str(e)
    return render(request, 'sync.html', {'sync': status, 'result': None, 'error': err})


@app.post('/sync')
def run_sync(request: Request, limit: int = Form(200), start_height: str = Form(''), scope: str = Form('account')):
    u = require_user(request)
    if not u:
        return RedirectResponse('/login', 303)
    a = get_active_account(request, u)
    start = int(start_height) if start_height.strip() != '' else None
    account_id = a['id'] if scope == 'account' else None
    try:
        result = sync_to_tip(limit=limit, start_height=start, account_id=account_id)
        err = None
        status = sync_status()
    except Exception as e:
        result = None
        err = str(e)
        status = {}
    return render(request, 'sync.html', {'sync': status, 'result': result, 'error': err})


@app.post('/sync/background')
def run_sync_background(request: Request, batch_size: int = Form(200), start_height: str = Form(''), scope: str = Form('account')):
    u = require_user(request)
    if not u:
        return RedirectResponse('/login', 303)
    a = get_active_account(request, u)
    start = int(start_height) if start_height.strip() != '' else None
    account_id = a['id'] if scope == 'account' else None
    try:
        start_background_sync(batch_size=batch_size, start_height=start, account_id=account_id, scope=scope)
    except Exception:
        pass
    return RedirectResponse('/sync', 303)


@app.post('/sync/background/stop')
def stop_sync_background(request: Request):
    u = require_user(request)
    if not u:
        return RedirectResponse('/login', 303)
    stop_background_sync()
    return RedirectResponse('/sync', 303)


@app.get('/sync/status.json')
def sync_status_json(request: Request):
    u = require_user(request)
    if not u:
        return JSONResponse({'error': 'not logged in'}, status_code=401)
    try:
        return JSONResponse(sync_status())
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@app.get('/send')
def send_page(request: Request):
    u = require_user(request)
    if not u:
        return RedirectResponse('/login', 303)
    a = get_active_account(request, u)
    return render(request, 'send.html', {'error': None, 'preview': None, 'utxos': spendable_utxos(a['id']), 'change_addresses': own_addresses_for_change(a['id'])})


@app.post('/send/preview')
def send_preview(
    request: Request,
    address: str = Form(...),
    amount: str = Form(...),
    fee_sats: int = Form(None),
    selected_utxos: list[str] = Form([]),
    change_mode: str = Form('new'),
    change_address: str = Form(''),
):
    u = require_user(request)
    if not u:
        return RedirectResponse('/login', 303)
    a = get_active_account(request, u)
    try:
        raw, ins, outs, fee = build_send(
            a['id'],
            address,
            amount,
            fee_sats,
            selected_utxos=selected_utxos,
            change_mode=change_mode,
            change_address=change_address or None,
        )
        return render(request, 'send.html', {
            'error': None,
            'utxos': spendable_utxos(a['id']),
            'change_addresses': own_addresses_for_change(a['id']),
            'preview': {
                'raw': raw, 'inputs': ins, 'outputs': outs, 'fee': fee,
                'fee_btc': fee / 100000000,
                'input_total_sats': sum(i['amount_sats'] for i in ins),
                'input_total_btc': sum(i['amount_sats'] for i in ins) / 100000000,
                'change_sats': sum(o['amount_sats'] for o in outs if o.get('kind') == 'Wechselgeld'),
                'change_btc': sum(o['amount_sats'] for o in outs if o.get('kind') == 'Wechselgeld') / 100000000,
                'address': address, 'amount': amount,
                'selected_utxos': selected_utxos, 'change_mode': change_mode, 'change_address': change_address,
            }
        })
    except Exception as e:
        return render(request, 'send.html', {
            'error': str(e),
            'preview': None,
            'utxos': spendable_utxos(a['id']),
            'change_addresses': own_addresses_for_change(a['id']),
        }, 400)


@app.post('/send/broadcast')
def broadcast(request: Request, rawtx: str = Form(...)):
    u = require_user(request)
    if not u:
        return RedirectResponse('/login', 303)
    try:
        txid = BitcoinRPC().call('sendrawtransaction', [rawtx])
        return render(request, 'sent.html', {'txid': txid})
    except Exception as e:
        a = get_active_account(request, u)
        return render(request, 'send.html', {'error': str(e), 'preview': None, 'utxos': spendable_utxos(a['id']), 'change_addresses': own_addresses_for_change(a['id'])}, 400)
