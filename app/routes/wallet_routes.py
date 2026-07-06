from fastapi import APIRouter, Request, Form
from starlette.responses import RedirectResponse
from ..main import render
from ..auth import current_user
from ..wallet_engine import create_key, all_users_public_addresses
from ..services.wallet_service import wallet_addresses, balance, build_payment_preview, broadcast_payment, wallet_meta

router = APIRouter(prefix='/wallet')

def must_user(request: Request):
    return current_user(request)

@router.get('')
def wallet_page(request: Request):
    user = must_user(request)
    if not user: return RedirectResponse('/login', status_code=303)
    return render(request, 'wallet.html', {
        'user': user,
        'wallet': wallet_meta(user['id']),
        'addresses': wallet_addresses(user['id']),
        'balances': balance(user['id']),
        'public_addresses': all_users_public_addresses(),
        'error': None,
        'success': None,
    })

@router.post('/address')
def new_address(request: Request, label: str = Form('')):
    user = must_user(request)
    if not user: return RedirectResponse('/login', status_code=303)
    create_key(user['id'], label)
    return RedirectResponse('/wallet', status_code=303)

@router.get('/send')
def send_page(request: Request):
    user = must_user(request)
    if not user: return RedirectResponse('/login', status_code=303)
    return render(request, 'send.html', {'user': user, 'preview': None, 'error': None})

@router.post('/send/preview')
def send_preview(request: Request, destination: str = Form(...), amount: str = Form(...), fee_sats: int = Form(1000)):
    user = must_user(request)
    if not user: return RedirectResponse('/login', status_code=303)
    try:
        preview = build_payment_preview(user['id'], destination.strip(), amount.strip(), fee_sats)
        return render(request, 'send.html', {'user': user, 'preview': preview, 'error': None})
    except Exception as e:
        return render(request, 'send.html', {'user': user, 'preview': None, 'error': str(e)}, status_code=400)

@router.post('/send/broadcast')
def send_broadcast(request: Request, destination: str = Form(...), amount: str = Form(...), fee_sats: int = Form(1000), change_address: str = Form("")):
    user = must_user(request)
    if not user: return RedirectResponse('/login', status_code=303)
    try:
        txid, preview = broadcast_payment(user['id'], destination.strip(), amount.strip(), fee_sats, change_address.strip() or None)
        return render(request, 'tx_result.html', {'user': user, 'txid': txid, 'preview': preview, 'error': None})
    except Exception as e:
        return render(request, 'tx_result.html', {'user': user, 'txid': None, 'preview': None, 'error': str(e)}, status_code=400)
