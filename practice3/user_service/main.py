import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import httpx
import jwt
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

app = FastAPI(title="User Service", version="1.0.0")

NOTIFY_URL = os.getenv("NOTIFY_URL", "http://localhost:8001/notify/")
POSTS_URL = os.getenv("POSTS_URL", "https://jsonplaceholder.typicode.com/posts")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me-0123456789abcdef")
ALGORITHM = "HS256"
TOKEN_TTL_MINUTES = 30


# Модели данных (Pydantic)
class UserBase(BaseModel):
    name: str
    email: str
    age: Optional[int] = None


class UserCreate(UserBase):
    pass


class User(UserBase):
    id: int
    created_at: datetime
    is_active: bool = True


class Notification(BaseModel):
    user_id: int
    email: str
    message: str


class Credentials(BaseModel):
    username: str
    password: str


# Хранилище (in-memory)
users_db = {}
next_user_id = 1
accounts_db = {}  # username -> пароль (в хешированном виде)


# Аутентификация (JWT)
def hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000).hex()


bearer = HTTPBearer(auto_error=False)


def create_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=TOKEN_TTL_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def require_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload["sub"]


@app.post("/signup", status_code=201)
async def signup(data: Credentials):
    if data.username in accounts_db:
        raise HTTPException(status_code=400, detail="Username already registered")
    salt = os.urandom(16)
    accounts_db[data.username] = (salt, hash_password(data.password, salt))
    return {"message": "Account created", "username": data.username}


@app.post("/login")
async def login(data: Credentials):
    account = accounts_db.get(data.username)
    if account is None or not hmac.compare_digest(
        account[1], hash_password(data.password, account[0])
    ):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    return {"access_token": create_token(data.username), "token_type": "bearer"}


# Корневой эндпоинт
@app.get("/")
async def root():
    return {"message": "User Service is running!", "docs": "/docs"}


# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# CRUD
@app.post("/users/", response_model=User, status_code=201)
async def create_user(user: UserCreate):
    global next_user_id
    # Проверка уникальности email
    for existing_user in users_db.values():
        if existing_user.email == user.email:
            raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        id=next_user_id,
        name=user.name,
        email=user.email,
        age=user.age,
        created_at=datetime.now(),
        is_active=True,
    )
    users_db[next_user_id] = new_user
    next_user_id += 1

    # Интеграция с Notification Service
    async with httpx.AsyncClient() as client:
        try:
            notification = Notification(
                user_id=new_user.id,
                email=new_user.email,
                message=f"Welcome, {new_user.name}!",
            )
            response = await client.post(
                NOTIFY_URL, json=notification.model_dump(), timeout=5.0
            )
            response.raise_for_status()
        except httpx.RequestError:
            # Логируем ошибку, но не прерываем создание пользователя
            print(f"Failed to send notification for user {new_user.id}")
        except httpx.HTTPStatusError:
            print(f"Notification service rejected request for user {new_user.id}")

    return new_user


@app.get("/users/", response_model=List[User])
async def get_users(skip: int = 0, limit: int = 10, min_age: Optional[int] = None):
    users_list = list(users_db.values())
    if min_age is not None:
        users_list = [u for u in users_list if u.age is not None and u.age > min_age]
    return users_list[skip : skip + limit]


@app.get("/users/{user_id}", response_model=User)
async def get_user(user_id: int):
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    return users_db[user_id]


@app.put("/users/{user_id}", response_model=User)
async def update_user(user_id: int, user: UserCreate, _: str = Depends(require_token)):
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    updated_user = users_db[user_id]
    updated_user.name = user.name
    updated_user.email = user.email
    updated_user.age = user.age
    return updated_user


@app.delete("/users/{user_id}")
async def delete_user(user_id: int, _: str = Depends(require_token)):
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    del users_db[user_id]
    return {"message": f"User {user_id} deleted successfully"}


# Интеграция с внешним API
@app.get("/users/{user_id}/posts")
async def get_user_posts(user_id: int):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                POSTS_URL, params={"userId": user_id}, timeout=5.0
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"External API returned {exc.response.status_code}",
            )
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="External API is unavailable")
    return response.json()
