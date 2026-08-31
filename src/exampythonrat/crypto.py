"""Module de chiffrement pour les communications TCP."""

import base64
import logging
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


def generate_key() -> bytes:
    """Génère une nouvelle clé Fernet."""
    return Fernet.generate_key()


def derive_key(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """Dérive une clé Fernet à partir d'un mot de passe via PBKDF2."""
    if salt is None:
        salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key, salt


class CryptoHandler:
    """Gère le chiffrement et déchiffrement des messages avec Fernet (AES-128-CBC + HMAC)."""

    def __init__(self, key: bytes):
        self._fernet = Fernet(key)
        logger.debug("CryptoHandler initialisé")

    def encrypt(self, data: bytes) -> bytes:
        """Chiffre des données brutes."""
        return self._fernet.encrypt(data)

    def decrypt(self, token: bytes) -> bytes:
        """Déchiffre un token Fernet."""
        return self._fernet.decrypt(token)
