from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path
from .config import get_settings
from .database import init_db
from .auth import current_user

settings = get_settings()
BASE = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=str(BASE / 'templates'))

app = FastAPI(title=settings.app_title)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site='lax')
app.mount('/static', StaticFiles(directory=str(BASE / 'static')), name='static')

@app.on_event('startup')
def startup():
    init_db()

@app.middleware('http')
async def add_common_context(request: Request, call_next):
    return await call_next(request)

def render(request: Request, template: str, context=None, status_code=200):
    base = {
        'request': request,
        'settings': settings,
        'user': current_user(request),
    }
    if context:
        base.update(context)
    return templates.TemplateResponse(request, template, base, status_code=status_code)

# import routes after render/app exist
from .routes import auth_routes, dashboard_routes, wallet_routes, explorer_routes  # noqa
app.include_router(auth_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(wallet_routes.router)
app.include_router(explorer_routes.router)
