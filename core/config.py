import os

_PLACEHOLDER_SECRET_KEY = "MY_SUPER_SECRET_KEY_WILL_BE_CHANGED"

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY or SECRET_KEY == _PLACEHOLDER_SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is not set (or is still the placeholder "
        "value). Set a long, random SECRET_KEY in .env before starting the app — "
        "e.g. python -c \"import secrets; print(secrets.token_urlsafe(48))\""
    )

ALGO = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
