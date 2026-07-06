from fastapi import APIRouter, Request
from starlette.responses import RedirectResponse
from ..main import render
from ..auth import current_user
from ..services.node_service import node_status
from ..services.wallet_service import balance, wallet_addresses, outgoing_history, wallet_meta

router = APIRouter()

@router.get('/')
def dashboard(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse('/login', status_code=303)
    status = node_status()
    bal = balance(user['id'])
    addresses = wallet_addresses(user['id'])
    history = outgoing_history(user['id'])
    meta = wallet_meta(user['id'])
    return render(request, 'dashboard.html', {
        'user': user,
        'wallet': meta,
        'chain': status['chain'],
        'network': status['network'],
        'mempool': status['mempool'],
        'balances': bal,
        'addresses': addresses,
        'history': history,
    })
