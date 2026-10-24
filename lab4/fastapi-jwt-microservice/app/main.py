import os
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm

from app import database
from app.auth import (
    audit,
    authenticate_user,
    check_rate_limit,
    create_user_with_hash,
    get_current_user,
    get_password_hash,
    issue_tokens,
    register_failure,
    require_role,
    reset_failures,
    verify_password,
    verify_refresh_token,
)
from app.database import blacklist_refresh_token as add_to_blacklist
from app.database import create_user, get_user_by_username
from app.models import PasswordChange, RefreshToken, Token, User, UserCreate, UserLogin

app = FastAPI(title="JWT Protected Microservice")

ALLOWED_ORIGINS = [o for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o]
ADMIN_CODE = os.getenv("ADMIN_CODE")

# CORS: доступ к API из браузера только с доверенных источников
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def csrf_origin_check(request: Request, call_next):
    """Защита от CSRF: запросы, изменяющие состояние, с чужим Origin отклоняются."""
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin and origin not in ALLOWED_ORIGINS:
            audit.warning("csrf blocked origin=%s path=%s", origin, request.url.path)
            return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
    return await call_next(request)


# ПУБЛИЧНЫЕ ЭНДПОИНТЫ (доступ без токена)
@app.get("/")
async def public_root():
    """Публичный эндпоинт - доступен всем"""
    return {
        "message": "Welcome to JWT Protected Microservice!",
        "public_info": "This is public information",
        "endpoints": {
            "public": ["/", "/public-info", "/docs", "/openapi.json"],
            "auth": ["/register", "/token", "/token/custom", "/refresh", "/logout",
                     "/token/revoke-all", "/password"],
            "protected": ["/protected", "/protected/admin"],
        },
    }


@app.get("/public-info")
async def public_info():
    """Публичный эндпоинт с ограниченной информацией"""
    return {
        "public_data": {"app_name": "JWT Microservice", "version": "1.0.0", "status": "operational"},
        "note": "Full information available only with authentication",
    }


# ЭНДПОИНТЫ АУТЕНТИФИКАЦИИ
@app.post("/register", status_code=201)
async def register(
    user_data: UserCreate,
    request: Request,
    x_admin_code: Optional[str] = Header(default=None),
):
    """Регистрация нового пользователя. Роль admin требует заголовок X-Admin-Code."""
    ip = request.client.host if request.client else "unknown"
    check_rate_limit(f"register:{ip}")
    if user_data.role == "admin" and (not ADMIN_CODE or x_admin_code != ADMIN_CODE):
        audit.warning("admin registration denied username=%s ip=%s", user_data.username, ip)
        raise HTTPException(status_code=403, detail="Admin role requires a valid X-Admin-Code")
    if get_user_by_username(user_data.username):
        register_failure(f"register:{ip}")
        raise HTTPException(status_code=400, detail="Username already registered")
    user = create_user_with_hash(user_data)
    create_user(user)
    audit.info("registered username=%s role=%s ip=%s", user.username, user.role, ip)
    return {"message": "User created successfully", "username": user.username,
            "email": user.email, "role": user.role}


def _login(username: str, password: str, request: Request) -> dict:
    ip = request.client.host if request.client else "unknown"
    key = f"login:{ip}:{username}"
    check_rate_limit(key)
    user = authenticate_user(username, password)
    if not user:
        register_failure(key)
        audit.warning("login failed username=%s ip=%s", username, ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    reset_failures(key)
    audit.info("login ok username=%s ip=%s", username, ip)
    return issue_tokens(user)


@app.post("/token", response_model=Token)
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    """Вход и получение токенов (OAuth2 форма)"""
    return _login(form_data.username, form_data.password, request)


@app.post("/token/custom", response_model=Token)
async def login_custom(login_data: UserLogin, request: Request):
    """Вход и получение токенов (JSON)"""
    return _login(login_data.username, login_data.password, request)


@app.post("/refresh", response_model=Token)
async def refresh_token(refresh_data: RefreshToken):
    """Обновление токенов по refresh токену (старый refresh отзывается)"""
    user, payload = verify_refresh_token(refresh_data.refresh_token)
    add_to_blacklist(refresh_data.refresh_token)
    audit.info("refresh username=%s", user.username)
    # auth_time сохраняется: общее время сессии ограничено MAX_SESSION_DAYS
    return issue_tokens(user, payload.get("auth_time"))


@app.post("/logout")
async def logout(refresh_data: RefreshToken):
    """Выход и отзыв refresh токена"""
    user, _ = verify_refresh_token(refresh_data.refresh_token)
    add_to_blacklist(refresh_data.refresh_token)
    audit.info("logout username=%s", user.username)
    return {"message": "Successfully logged out"}


@app.post("/token/revoke-all")
async def revoke_all(current_user: User = Depends(get_current_user)):
    """Отзывает все токены (access и refresh) текущего пользователя"""
    version = database.revoke_all_tokens(current_user.username)
    audit.info("revoke-all username=%s version=%s", current_user.username, version)
    return {"message": "All tokens revoked", "token_version": version}


@app.post("/password")
async def change_password(data: PasswordChange, current_user: User = Depends(get_current_user)):
    """Смена пароля; все выданные ранее токены становятся недействительными"""
    if not verify_password(data.old_password, current_user.password_hash):
        audit.warning("password change failed username=%s", current_user.username)
        raise HTTPException(status_code=400, detail="Old password is incorrect")
    current_user.password_hash = get_password_hash(data.new_password)
    database.revoke_all_tokens(current_user.username)
    audit.info("password changed username=%s", current_user.username)
    return {"message": "Password changed, please login again"}


# ЗАЩИЩЕННЫЕ ЭНДПОИНТЫ (доступ только по токену)
@app.get("/protected")
async def protected_endpoint(current_user: User = Depends(get_current_user)):
    """Защищенный эндпоинт - доступен только авторизованным пользователям"""
    return {
        "message": f"Hello, {current_user.username}! This is protected information",
        "user_data": {
            "username": current_user.username,
            "email": current_user.email,
            "role": current_user.role,
            "created_at": current_user.created_at.isoformat(),
        },
    }


@app.get("/protected/admin")
async def admin_endpoint(current_user: User = Depends(require_role("admin"))):
    """Административный эндпоинт - только для роли admin"""
    return {"message": "Admin panel", "users": list(database.fake_users_db.keys())}
