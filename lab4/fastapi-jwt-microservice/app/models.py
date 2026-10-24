from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Модель пользователя
class User(BaseModel):
    username: str
    email: EmailStr
    password_hash: str
    role: Literal["user", "admin"] = "user"
    disabled: bool = False
    token_version: int = 0  # увеличивается при отзыве всех токенов
    created_at: datetime = Field(default_factory=_now)


# Модель для регистрации
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Literal["user", "admin"] = "user"


# Модель для входа (логин)
class UserLogin(BaseModel):
    username: str
    password: str


# Модель токена
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# Модель обновления токена
class RefreshToken(BaseModel):
    refresh_token: str


# Смена пароля
class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)


# Данные пользователя в токене
class TokenData(BaseModel):
    username: Optional[str] = None
