"""Opaque, expiring sessions. Only token hashes are persisted."""
import hashlib
import secrets
from datetime import datetime, timedelta
from database import AuthSession, SessionLocal


def issue_token(usuario: str) -> str:
    token = "sess_" + secrets.token_urlsafe(32)
    now = datetime.utcnow()
    with SessionLocal() as db:
        db.query(AuthSession).filter(AuthSession.expires_at <= now).delete()
        db.add(AuthSession(token_hash=_digest(token), usuario=usuario,
                           expires_at=now + timedelta(days=30)))
        db.commit()
    return token


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def token_user(token: str) -> str | None:
    if not token or not token.startswith("sess_") or len(token) > 256:
        return None
    with SessionLocal() as db:
        row = db.get(AuthSession, _digest(token))
        if row is None or row.expires_at <= datetime.utcnow():
            return None
        return row.usuario
