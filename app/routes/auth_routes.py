from fastapi import APIRouter, Request, Form
from starlette.responses import RedirectResponse
from sqlite3 import IntegrityError
from ..main import render
from ..auth import authenticate, create_user, login_response, logout_response, current_user
from ..services.wallet_service import ensure_first_address

router = APIRouter()

@router.get('/login')
def login_page(request: Request):
    if current_user(request):
        return RedirectResponse('/', status_code=303)
    return render(request, 'login.html', {'error': None})

@router.post('/login')
def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    user = authenticate(username, password)
    if not user:
        return render(request, 'login.html', {'error': 'Login fehlgeschlagen.'}, status_code=401)
    ensure_first_address(user['id'])
    return login_response(request, user)

@router.get('/register')
def register_page(request: Request):
    return render(request, 'register.html', {'error': None})

@router.post('/register')
def register_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    try:
        user = create_user(username, password)
        ensure_first_address(user['id'])
    except IntegrityError:
        return render(request, 'register.html', {'error': 'Benutzername existiert bereits.'}, status_code=400)
    except ValueError as e:
        return render(request, 'register.html', {'error': str(e)}, status_code=400)
    return login_response(request, user)

@router.post('/logout')
def logout(request: Request):
    return logout_response(request)
