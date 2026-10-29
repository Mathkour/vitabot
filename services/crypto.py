import os

from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()


def _get_fernet() -> Fernet:
    key = os.getenv("CLIENT_CREDENTIALS_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("CLIENT_CREDENTIALS_ENCRYPTION_KEY is not set")
    return Fernet(key.encode())


def encrypt_value(plain: str) -> str:
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_value(token: str) -> str:
    return _get_fernet().decrypt(token.encode()).decode()
