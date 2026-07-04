from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .auth import require_basic_auth
from .config import get_settings
from .rpc import BitcoinRPC, BitcoinRPCError, RPCConfig

settings = get_settings()
app = FastAPI(title=settings.app_title, dependencies=[Depends(require_basic_auth)])
app.mount('/static', StaticFiles(directory='app/static'), name='static')
templates = Jinja2Templates(directory='app/templates')


def rpc_client() -> BitcoinRPC:
    s = get_settings()
    return BitcoinRPC(RPCConfig(
        scheme=s.bitcoin_rpc_scheme,
        host=s.bitcoin_rpc_host,
        port=s.bitcoin_rpc_port,
        user=s.bitcoin_rpc_user,
        password=s.bitcoin_rpc_password,
        wallet=s.bitcoin_rpc_wallet,
        timeout=s.bitcoin_rpc_timeout,
    ))


def render(request: Request, template: str, context: dict[str, Any], status_code: int = 200) -> HTMLResponse:
    base = {'request': request, 'settings': get_settings(), 'warning': 'Private Chain / Experimentell – nicht für produktiven Mainnet-Betrieb verwenden.'}
    base.update(context)
    return templates.TemplateResponse(template, base, status_code=status_code)


def render_rpc_error(request: Request, exc: BitcoinRPCError) -> HTMLResponse:
    return render(request, 'error.html', {'error': str(exc), 'code': exc.code, 'details': exc.details}, 502)


@app.get('/', response_class=HTMLResponse)
def dashboard(request: Request):
    rpc = rpc_client()
    try:
        chain = rpc.get_blockchain_info()
        network = rpc.get_network_info()
        mempool = rpc.get_mempool_info()
        balances = rpc.get_balances() if get_settings().bitcoin_rpc_wallet else {}
        wallet_info = rpc.get_wallet_info() if get_settings().bitcoin_rpc_wallet else {}
    except BitcoinRPCError as exc:
        return render_rpc_error(request, exc)
    return render(request, 'dashboard.html', {
        'chain': chain,
        'network': network,
        'mempool': mempool,
        'balances': balances,
        'wallet_info': wallet_info,
    })


@app.get('/wallet', response_class=HTMLResponse)
def wallet(request: Request):
    rpc = rpc_client()
    try:
        balances = rpc.get_balances()
        wallet_info = rpc.get_wallet_info()
        addresses = rpc.list_received_by_address()
        unspent = rpc.list_unspent()
        transactions = rpc.list_transactions(100)
    except BitcoinRPCError as exc:
        return render_rpc_error(request, exc)
    return render(request, 'wallet.html', {
        'balances': balances,
        'wallet_info': wallet_info,
        'addresses': addresses,
        'unspent': unspent,
        'transactions': transactions,
    })


@app.post('/wallet/new-address')
def new_address(label: str = Form(default='')):
    rpc = rpc_client()
    address = rpc.get_new_address(label=label)
    return RedirectResponse(f'/wallet?new_address={address}', status_code=303)


@app.get('/send', response_class=HTMLResponse)
def send_page(request: Request):
    return render(request, 'send.html', {'preview': None, 'txid': None})


@app.post('/send/preview', response_class=HTMLResponse)
def send_preview(request: Request, address: str = Form(...), amount: float = Form(...), fee_rate: str = Form(default='')):
    try:
        balances = rpc_client().get_balances()
    except BitcoinRPCError as exc:
        return render_rpc_error(request, exc)
    preview = {'address': address, 'amount': amount, 'fee_rate': fee_rate.strip(), 'balances': balances}
    return render(request, 'send.html', {'preview': preview, 'txid': None})


@app.post('/send/confirm', response_class=HTMLResponse)
def send_confirm(request: Request, address: str = Form(...), amount: float = Form(...), fee_rate: str = Form(default='')):
    try:
        fee = float(fee_rate) if fee_rate.strip() else None
        txid = rpc_client().send_to_address(address, amount, fee)
    except (BitcoinRPCError, ValueError) as exc:
        if isinstance(exc, BitcoinRPCError):
            return render_rpc_error(request, exc)
        return render(request, 'send.html', {'preview': None, 'txid': None, 'form_error': 'Fee-Rate ist keine gültige Zahl.'}, 400)
    return render(request, 'send.html', {'preview': None, 'txid': txid})


@app.get('/mempool', response_class=HTMLResponse)
def mempool(request: Request, txid: str | None = None):
    rpc = rpc_client()
    try:
        info = rpc.get_mempool_info()
        txids = rpc.get_raw_mempool(False)
        tx = rpc.get_raw_transaction(txid, True) if txid else None
    except BitcoinRPCError as exc:
        return render_rpc_error(request, exc)
    return render(request, 'mempool.html', {'info': info, 'txids': txids, 'selected_txid': txid, 'tx': tx})


@app.get('/block', response_class=HTMLResponse)
def block_page(request: Request, q: str | None = None):
    block = None
    error = None
    if q:
        try:
            rpc = rpc_client()
            block_hash = rpc.get_block_hash(int(q)) if q.isdigit() else q
            block = rpc.get_block(block_hash, 2)
        except (BitcoinRPCError, ValueError) as exc:
            error = str(exc)
    return render(request, 'block.html', {'block': block, 'q': q or '', 'lookup_error': error})
