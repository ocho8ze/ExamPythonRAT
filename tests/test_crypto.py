"""Tests unitaires pour le module crypto."""

import pytest

from exampythonrat.crypto import CryptoHandler, derive_key, generate_key


class TestGenerateKey:
    def test_returns_bytes(self):
        key = generate_key()
        assert isinstance(key, bytes)

    def test_key_length(self):
        key = generate_key()
        assert len(key) == 44

    def test_unique_keys(self):
        key1 = generate_key()
        key2 = generate_key()
        assert key1 != key2


class TestDeriveKey:
    def test_derive_produces_valid_key(self):
        key, salt = derive_key("motdepasse")
        assert isinstance(key, bytes)
        assert len(key) == 44
        assert isinstance(salt, bytes)
        assert len(salt) == 16

    def test_same_password_same_salt_same_key(self):
        key1, salt = derive_key("test123")
        key2, _ = derive_key("test123", salt)
        assert key1 == key2

    def test_different_passwords_different_keys(self):
        key1, salt = derive_key("password1")
        key2, _ = derive_key("password2", salt)
        assert key1 != key2

    def test_different_salts_different_keys(self):
        key1, salt1 = derive_key("samepassword")
        key2, salt2 = derive_key("samepassword")
        assert salt1 != salt2
        assert key1 != key2


class TestCryptoHandler:
    @pytest.fixture()
    def handler(self):
        key = generate_key()
        return CryptoHandler(key)

    def test_encrypt_returns_bytes(self, handler):
        encrypted = handler.encrypt(b"hello")
        assert isinstance(encrypted, bytes)

    def test_encrypt_decrypt_roundtrip(self, handler):
        original = b"message secret"
        encrypted = handler.encrypt(original)
        decrypted = handler.decrypt(encrypted)
        assert decrypted == original

    def test_encrypt_decrypt_empty(self, handler):
        encrypted = handler.encrypt(b"")
        decrypted = handler.decrypt(encrypted)
        assert decrypted == b""

    def test_encrypt_decrypt_binary(self, handler):
        original = bytes(range(256))
        encrypted = handler.encrypt(original)
        decrypted = handler.decrypt(encrypted)
        assert decrypted == original

    def test_encrypted_differs_from_plaintext(self, handler):
        original = b"cleartext"
        encrypted = handler.encrypt(original)
        assert encrypted != original

    def test_different_keys_cannot_decrypt(self):
        handler1 = CryptoHandler(generate_key())
        handler2 = CryptoHandler(generate_key())
        encrypted = handler1.encrypt(b"secret")
        with pytest.raises(Exception):
            handler2.decrypt(encrypted)
