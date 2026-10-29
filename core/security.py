import bcrypt
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from fastapi import Response
from core.config import SECRET_KEY, ALGO, ACCESS_TOKEN_EXPIRE_MINUTES

ACCESS_TOKEN_COOKIE_NAME = "access_token"


def hash_password(plain_password: str) -> str:
    pwd_bytes = plain_password.encode("utf-8")
    if len(pwd_bytes) > 72:
        raise ValueError("Password too long (max 72 bytes)")
    hashed = bcrypt.hashpw(pwd_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    try:
        pwd_bytes = plain_password.encode("utf-8")
        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hashed_bytes)
    except (ValueError, TypeError):
        return False


def create_access_token(data: dict, expire_minutes: int | None = None) -> str:
    to_encode = data.copy()
    minutes = expire_minutes if expire_minutes is not None else ACCESS_TOKEN_EXPIRE_MINUTES
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGO)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGO])
    except JWTError:
        return None


def set_auth_cookie(response: Response, token: str) -> None:
    # No max_age: this is a browser-session cookie by design, meant to die
    # when the browser fully closes rather than persist across restarts.
    # The JWT's own "exp" claim (ACCESS_TOKEN_EXPIRE_MINUTES) remains the
    # real, server-enforced expiry — decode_access_token() rejects an
    # expired token regardless of whether the cookie itself is still around.
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE_NAME,
        value="",
        httponly=True,
        secure=True,
        samesite="none",
        max_age=0,
        path="/",
    )