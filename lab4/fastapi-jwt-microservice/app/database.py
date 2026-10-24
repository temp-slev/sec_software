from typing import Dict

from app.models import User

# База данных в памяти
fake_users_db: Dict[str, User] = {}
refresh_tokens_blacklist: set = set()


def get_user_by_username(username: str) -> User | None:
    return fake_users_db.get(username)


def create_user(user: User) -> User:
    fake_users_db[user.username] = user
    return user


def blacklist_refresh_token(token: str):
    refresh_tokens_blacklist.add(token)


def is_token_blacklisted(token: str) -> bool:
    return token in refresh_tokens_blacklist


def revoke_all_tokens(username: str) -> int:
    """Отзывает все токены пользователя: старая версия токенов перестаёт быть валидной."""
    user = fake_users_db[username]
    user.token_version += 1
    return user.token_version
