from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .auth import current_user, require_basic_auth, require_user
from .config import get_settings
from .db import add_user_address, authenticate_user, create_user, init_db, list_public_users, list_user_addresses
from .rpc import BitcoinRPCError
from .wallets import ensure_wallet_loaded, export_private_key, node_rpc, wallet_rpc

settings = get_settings()
app = FastAPI(title=settings.app_title)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site='lax')
app.mount('/static', StaticFiles(directory='app/static'), name='static')
templates = Jinja2Templates(directory='app/templates')


@app.on_event('startup')
def startup() -> None:
    init_db()


def render(request: Request, template: str, context: dict[str, Any], status_code: int = 200) -> HTMLResponse:
    base = {
        'request': request,
        'settings': get_settings(),
        'user': current_user(request),
        'warning': 'Private Chain / Experimentell – nicht für produktiven Mainnet-Betrieb verwenden.',
    }
    base.update(context)
    return templates.TemplateResponse(template, base, status_code=status_code)


def render_rpc_error(request: Request, exc: BitcoinRPCError) -> HTMLResponse:
    return render(request, 'error.html', {'error': str(exc), 'code': exc.code, 'details': exc.details}, 502)


def my_wallet(user: dict):
    wallet_name = user['wallet_name']
    ensure_wallet_loaded(wallet_name)
    return wallet_rpc(wallet_name)


@app.get('/login', response_class=HTMLResponse, dependencies=[Depends(require_basic_auth)])
def login_page(request: Request):
    return render(request, 'login.html', {'error': None})


@app.post('/login', response_class=HTMLResponse, dependencies=[Depends(require_basic_auth)])
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = authenticate_user(username, password)
    if not user:
        return render(request, 'login.html', {'error': 'Benutzername oder Passwort falsch.'}, 401)
    try:
        ensure_wallet_loaded(user['wallet_name'])
    except BitcoinRPCError as exc:
        return render_rpc_error(request, exc)
    request.session['user_id'] = user['id']
    return RedirectResponse('/', status_code=303)


@app.get('/register', response_class=HTMLResponse, dependencies=[Depends(require_basic_auth)])
def register_page(request: Request):
    if not get_settings().allow_registration:
        return render(request, 'login.html', {'error': 'Registrierung ist deaktiviert.'}, 403)
    return render(request, 'register.html', {'error': None})


@app.post('/register', response_class=HTMLResponse, dependencies=[Depends(require_basic_auth)])
def register(request: Request, username: str = Form(...), password: str = Form(...)):
    if not get_settings().allow_registration:
        return render(request, 'login.html', {'error': 'Registrierung ist deaktiviert.'}, 403)
    try:
        user = create_user(username, password)
        ensure_wallet_loaded(user['wallet_name'])
    except (ValueError, BitcoinRPCError) as exc:
        tmpl = 'register.html' if isinstance(exc, ValueError) else 'error.html'
        if isinstance(exc, BitcoinRPCError):
            return render_rpc_error(request, exc)
        return render(request, tmpl, {'error': str(exc)}, 400)
    request.session['user_id'] = user['id']
    return RedirectResponse('/', status_code=303)


@app.post('/logout')
def logout(request: Request):
    request.session.clear()
    return RedirectResponse('/login', status_code=303)


@app.get('/', response_class=HTMLResponse, dependencies=[Depends(require_basic_auth)])
def dashboard(request: Request, user: dict = Depends(require_user)):
    try:
        nrpc = node_rpc()
        wrpc = my_wallet(user)
        chain = nrpc.get_blockchain_info()
        network = nrpc.get_network_info()
        mempool = nrpc.get_mempool_info()
        balances = wrpc.get_balances()
        wallet_info = wrpc.get_wallet_info()
    except BitcoinRPCError as exc:
        return render_rpc_error(request, exc)
    return render(request, 'dashboard.html', {
        'chain': chain,
        'network': network,
        'mempool': mempool,
        'balances': balances,
        'wallet_info': wallet_info,
        'my_addresses': list_user_addresses(user['id']),
    })


@app.get('/wallet', response_class=HTMLResponse, dependencies=[Depends(require_basic_auth)])
def wallet(request: Request, show_key: str | None = None, user: dict = Depends(require_user)):
    try:
        wrpc = my_wallet(user)
        balances = wrpc.get_balances()
        wallet_info = wrpc.get_wallet_info()
        core_addresses = wrpc.list_received_by_address()
        unspent = wrpc.list_unspent()
        transactions = wrpc.list_transactions(100)
        private_key = export_private_key(user['wallet_name'], show_key) if show_key else None
    except BitcoinRPCError as exc:
        return render_rpc_error(request, exc)
    return render(request, 'wallet.html', {
        'balances': balances,
        'wallet_info': wallet_info,
        'addresses': core_addresses,
        'my_addresses': list_user_addresses(user['id']),
        'unspent': unspent,
        'transactions': transactions,
        'private_key_address': show_key,
        'private_key': private_key,
    })


@app.post('/wallet/new-address', dependencies=[Depends(require_basic_auth)])
def new_address(request: Request, label: str = Form(default=''), user: dict = Depends(require_user)):
    try:
        wrpc = my_wallet(user)
        final_label = label.strip() or f"{user['username']}"
        address = wrpc.get_new_address(label=f"app:{user['username']}:{final_label}")
        add_user_address(user['id'], address, final_label, user['wallet_name'])
    except BitcoinRPCError as exc:
        return render_rpc_error(request, exc)
    return RedirectResponse(f'/wallet?new_address={address}', status_code=303)


@app.get('/users', response_class=HTMLResponse, dependencies=[Depends(require_basic_auth)])
def users_page(request: Request, user: dict = Depends(require_user)):
    return render(request, 'users.html', {'users': list_public_users()})


@app.get('/send', response_class=HTMLResponse, dependencies=[Depends(require_basic_auth)])
def send_page(request: Request, user: dict = Depends(require_user)):
    return render(request, 'send.html', {'preview': None, 'txid': None, 'users': list_public_users()})


@app.post('/send/preview', response_class=HTMLResponse, dependencies=[Depends(require_basic_auth)])
def send_preview(request: Request, address: str = Form(...), amount: float = Form(...), fee_rate: str = Form(default=''), user: dict = Depends(require_user)):
    try:
        balances = my_wallet(user).get_balances()
    except BitcoinRPCError as exc:
        return render_rpc_error(request, exc)
    preview = {'address': address, 'amount': amount, 'fee_rate': fee_rate.strip(), 'balances': balances, 'from_wallet': user['wallet_name']}
    return render(request, 'send.html', {'preview': preview, 'txid': None, 'users': list_public_users()})


@app.post('/send/confirm', response_class=HTMLResponse, dependencies=[Depends(require_basic_auth)])
def send_confirm(request: Request, address: str = Form(...), amount: float = Form(...), fee_rate: str = Form(default=''), user: dict = Depends(require_user)):
    try:
        fee = float(fee_rate) if fee_rate.strip() else None
        txid = my_wallet(user).send_to_address(address, amount, fee)
    except (BitcoinRPCError, ValueError) as exc:
        if isinstance(exc, BitcoinRPCError):
            return render_rpc_error(request, exc)
        return render(request, 'send.html', {'preview': None, 'txid': None, 'form_error': 'Fee-Rate ist keine gültige Zahl.', 'users': list_public_users()}, 400)
    return render(request, 'send.html', {'preview': None, 'txid': txid, 'users': list_public_users()})


@app.get('/mempool', response_class=HTMLResponse, dependencies=[Depends(require_basic_auth)])
def mempool(request: Request, txid: str | None = None, user: dict = Depends(require_user)):
    rpc = node_rpc()
    try:
        info = rpc.get_mempool_info()
        txids = rpc.get_raw_mempool(False)
        tx = rpc.get_raw_transaction(txid, True) if txid else None
    except BitcoinRPCError as exc:
        return render_rpc_error(request, exc)
    return render(request, 'mempool.html', {'info': info, 'txids': txids, 'selected_txid': txid, 'tx': tx})


@app.get('/block', response_class=HTMLResponse, dependencies=[Depends(require_basic_auth)])
def block_page(request: Request, q: str | None = None, user: dict = Depends(require_user)):
    block = None
    error = None
    if q:
        try:
            rpc = node_rpc()
            block_hash = rpc.get_block_hash(int(q)) if q.isdigit() else q
            block = rpc.get_block(block_hash, 2)
        except (BitcoinRPCError, ValueError) as exc:
            error = str(exc)
    return render(request, 'block.html', {'block': block, 'q': q or '', 'lookup_error': error})
