import secrets

from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt_sha256", "bcrypt"], deprecated="auto")


def _argon2_hasher(salt: bytes) -> Argon2id:
    return Argon2id(
        salt=salt,
        length=32,
        iterations=3,
        lanes=1,
        memory_cost=64 * 1024,
    )


def hash_password(plain_password: str) -> str:
    salt = secrets.token_bytes(16)
    return _argon2_hasher(salt).derive_phc_encoded(plain_password.encode("utf-8"))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if hashed_password.startswith("$argon2id$"):
        try:
            Argon2id.verify_phc_encoded(plain_password.encode("utf-8"), hashed_password)
            return True
        except InvalidKey:
            return False
    return pwd_context.verify(plain_password, hashed_password)


def password_needs_rehash(hashed_password: str) -> bool:
    return not hashed_password.startswith("$argon2id$")
