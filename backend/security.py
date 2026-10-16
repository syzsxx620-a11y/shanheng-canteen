import hashlib
import secrets
from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .models import AuthSession, User, AuditLog

hasher = PasswordHasher()
bearer = HTTPBearer(auto_error=False)

def verify_password(encoded, password):
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False

def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def token_pair(db, user, session=None):
    secret = settings().jwt_secret
    if len(secret) < 32:
        raise HTTPException(503, '请先运行 python -m backend.cli init 配置密钥和数据库')
    refresh = secrets.token_urlsafe(48)
    if session is None:
        session = AuthSession(user_id=user.id)
        db.add(session)
    session.refresh_hash = digest(refresh)
    session.expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    db.flush()
    access = jwt.encode({'sub': user.id, 'sid': session.id, 'exp': datetime.now(timezone.utc)+timedelta(minutes=15)}, secret, algorithm='HS256')
    return {'access_token': access, 'refresh_token': refresh, 'token_type': 'bearer', 'expires_in': 900}

def current_user(token: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    try:
        if not token:
            raise ValueError()
        claims = jwt.decode(token.credentials, settings().jwt_secret, algorithms=['HS256'], options={'require': ['exp', 'sub', 'sid']})
        session = db.get(AuthSession, claims['sid'])
        user = db.get(User, claims['sub'])
        if not session or session.revoked or session.user_id != claims['sub'] or datetime.fromisoformat(session.expires_at) <= datetime.now(timezone.utc) or not user or not user.active:
            raise ValueError()
        return user
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, '登录已过期，请重新登录')

def manager(user: User = Depends(current_user)):
    if user.role not in ('canteen_admin', 'system_admin'):
        raise HTTPException(403, '需要管理员权限')
    return user

def system_admin(user: User = Depends(current_user)):
    if user.role != 'system_admin':
        raise HTTPException(403, '需要系统管理员权限')
    return user

def check_canteen(user, canteen_id):
    if user.role != 'system_admin' and user.canteen_id != canteen_id:
        raise HTTPException(403, '无权管理该食堂')

def revoke_all(db, user_id):
    for session in db.scalars(select(AuthSession).where(AuthSession.user_id == user_id)):
        session.revoked = True

def audit(db, user, action, target='', detail=None):
    db.add(AuditLog(user_id=user.id if user else None, action=action, target=target, detail=detail or {}))
