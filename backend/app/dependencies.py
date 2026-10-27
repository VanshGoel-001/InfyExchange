import logging

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services.auth import decode_access_token


security = HTTPBearer()

security_logger = logging.getLogger("security")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    request: Request = None,
    db: Session = Depends(get_db),
) -> User:

    token = credentials.credentials
    client_ip = request.client.host if request and request.client else "unknown"

    try:
        user_id = decode_access_token(token)
    except Exception:
        security_logger.warning("auth_failed reason=invalid_token ip=%s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user = db.get(User, user_id)

    if not user:
        security_logger.warning("auth_failed reason=user_not_found ip=%s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        security_logger.warning("deactivated_account_access user_id=%s ip=%s", user.id, client_ip)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact an administrator.",
        )

    return user


def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_admin:
        security_logger.warning(
            "admin_access_denied user_id=%s",
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required.",
        )
    return current_user