from fastapi import APIRouter, Request, Form
from starlette.responses import RedirectResponse
from ..main import render
from ..auth import current_user
from ..bitcoin_rpc import BitcoinRPC

router = APIRouter(prefix='/explorer')
rpc = BitcoinRPC()

@router.get('')
def explorer(request: Request):
    if not current_user(request): return RedirectResponse('/login', status_code=303)
    return render(request, 'explorer.html', {'result': None, 'query': '', 'error': None})

@router.post('')
def explorer_lookup(request: Request, query: str = Form(...)):
    if not current_user(request): return RedirectResponse('/login', status_code=303)
    q = query.strip()
    try:
        if q.isdigit():
            h = rpc.call('getblockhash', [int(q)])
            result = rpc.call('getblock', [h, 2])
        elif len(q) == 64:
            # Try block first, then tx.
            try:
                result = rpc.call('getblock', [q, 2])
            except Exception:
                result = rpc.call('getrawtransaction', [q, True])
        else:
            raise ValueError('Bitte Blockhöhe, Blockhash oder TXID eingeben.')
        return render(request, 'explorer.html', {'result': result, 'query': q, 'error': None})
    except Exception as e:
        return render(request, 'explorer.html', {'result': None, 'query': q, 'error': str(e)}, status_code=400)
