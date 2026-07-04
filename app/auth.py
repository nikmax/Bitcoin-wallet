import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .config import get_settings

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
