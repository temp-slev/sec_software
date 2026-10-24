import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.database import get_user_by_username, is_token_blacklisted
from app.models import TokenData, User

load_dotenv()

# Конфигурация JWT. SECRET_KEY обязателен: без него приложение не запускается.
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not set: create .env (see .env.example)")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
MAX_SESSION_DAYS = int(os.getenv("MAX_SESSION_DAYS", "30"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Аудит попыток аутентификации
audit = logging.getLogger("audit")
if not audit.handlers:
    audit.setLevel(logging.INFO)
    for handler in (logging.StreamHandler(), logging.FileHandler("audit.log", encoding="utf-8")):
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        audit.addHandler(handler)

# Защита от перебора: не более MAX_FAILED неудачных попыток за окно
MAX_FAILED = 5
WINDOW_SECONDS = 60
_failed: dict[str, list[float]] = {}


def check_rate_limit(key: str):
    now = time.monotonic()
    attempts = [t for t in _failed.get(key, []) if now - t < WINDOW_SECONDS]
    _failed[key] = attempts
    if len(attempts) >= MAX_FAILED:
        audit.warning("rate limit exceeded key=%s", key)
        raise HTTPException(status_code=429, detail="Too many failed attempts, try later")


def register_failure(key: str):
    _failed.setdefault(key, []).append(time.monotonic())


def reset_failures(key: str):
    _failed.pop(key, None)


# Хеширование пароля
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


# Создание пользователя (хеширование пароля)
def create_user_with_hash(user_data) -> User:
    return User(
        username=user_data.username,
        email=user_data.email,
        password_hash=get_password_hash(user_data.password),
        role=user_data.role,
    )


# Аутентификация пользователя
def authenticate_user(username: str, password: str) -> User | None:
    user = get_user_by_username(username)
    if not user or user.disabled:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def _encode(data: dict, token_type: str, expires: timedelta, extra: dict | None = None) -> str:
    to_encode = data.copy()
    to_encode.update(extra or {})
    to_encode.update({"exp": datetime.now(timezone.utc) + expires, "type": token_type,
                      "jti": uuid.uuid4().hex})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def _claims(user: User, auth_time: int | None = None) -> dict:
    return {"sub": user.username, "ver": user.token_version,
            "auth_time": auth_time or int(time.time())}


# Создание access токена
def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    return _encode(data, "access",
                   expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))


# Создание refresh токена
def create_refresh_token(data: dict) -> str:
    return _encode(data, "refresh", timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))


def issue_tokens(user: User, auth_time: int | None = None) -> dict:
    claims = _claims(user, auth_time)
    return {
        "access_token": create_access_token(claims),
        "refresh_token": create_refresh_token(claims),
        "token_type": "bearer",
    }


# Получение текущего пользователя из access токена
async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise credentials_exception
    if payload.get("type") != "access" or payload.get("sub") is None:
        raise credentials_exception
    token_data = TokenData(username=payload["sub"])
    user = get_user_by_username(token_data.username)
    if user is None or user.disabled or payload.get("ver") != user.token_version:
        raise credentials_exception
    return user


def require_role(role: str):
    async def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != role:
            audit.warning("forbidden user=%s required_role=%s", current_user.username, role)
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user

    return checker


# Проверка refresh токена (не истёк, не в blacklist, версия актуальна)
def verify_refresh_token(refresh_token: str) -> tuple[User, dict]:
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")
    username = payload.get("sub")
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = get_user_by_username(username)
    if user is None or user.disabled:
        raise HTTPException(status_code=401, detail="User not found")
    if is_token_blacklisted(refresh_token) or payload.get("ver") != user.token_version:
        raise HTTPException(status_code=401, detail="Token revoked")
    if time.time() - payload.get("auth_time", 0) > MAX_SESSION_DAYS * 86400:
        raise HTTPException(status_code=401, detail="Session expired, login again")
    return user, payload
