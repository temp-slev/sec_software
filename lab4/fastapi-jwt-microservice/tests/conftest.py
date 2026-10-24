import os

# Переменные окружения должны быть заданы до импорта приложения
os.environ["SECRET_KEY"] = "test-secret-key-for-unit-tests-only-0123456789"
os.environ["ADMIN_CODE"] = "admin-code"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "5"
