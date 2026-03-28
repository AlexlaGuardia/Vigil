"""API key generation and verification."""

import hashlib
import secrets


KEY_PREFIX = "vgl_"


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key. Returns (plaintext_key, key_hash, key_prefix)."""
    raw = secrets.token_urlsafe(32)
    plaintext = f"{KEY_PREFIX}{raw}"
    key_hash = hash_key(plaintext)
    prefix = plaintext[:12]
    return plaintext, key_hash, prefix


def hash_key(key: str) -> str:
    """SHA-256 hash of an API key."""
    return hashlib.sha256(key.encode()).hexdigest()


def verify_key(key: str, key_hash: str) -> bool:
    """Verify an API key against its stored hash."""
    return hashlib.sha256(key.encode()).hexdigest() == key_hash
