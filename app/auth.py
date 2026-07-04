from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .config import get_settings
from .db import get_user_by_id

security = HTTPBasic(auto_error=False)


def require_basic_auth(credentials: Annotated[HTTPBasicCredentials | None, Depends(security)] = None) -> None:
    settings = get_settings()
    if not settings.web_auth_user and not settings.web_auth_password:
        return
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, headers={'WWW-Authenticate': 'Basic'})
    valid_user = secrets.compare_digest(credentials.username, settings.web_auth_user)
    valid_password = secrets.compare_digest(credentials.password, settings.web_auth_password)
    if not (valid_user and valid_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, headers={'WWW-Authenticate': 'Basic'})


def current_user(request: Request) -> dict | None:
    user_id = request.session.get('user_id')
    if not user_id:
        return None
    return get_user_by_id(int(user_id))


def require_user(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={'Location': '/login'})
    return user
