"""Fernet symmetric encryption for Aeries credentials stored at rest."""
import base64
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet:
    """Return a Fernet instance, auto-generating a key if one isn't configured."""
    from app.config import settings as _settings
    key = _settings.SUBPLOT_ENCRYPTION_KEY or os.environ.get("SUBPLOT_ENCRYPTION_KEY", "")
    if not key:
        # Generate a one-time key and warn — fine for local dev, dangerous in production.
        key = Fernet.generate_key().decode()
        logger.warning(
            "SUBPLOT_ENCRYPTION_KEY not set — generated ephemeral key. "
            "Encrypted credentials will not survive a restart. "
            "Set SUBPLOT_ENCRYPTION_KEY in your .env file."
        )
        # Cache for the lifetime of this process so repeated calls are consistent.
        os.environ["SUBPLOT_ENCRYPTION_KEY"] = key
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(text: str) -> str:
    """Encrypt *text* and return a base64url-encoded ciphertext string."""
    fernet = _get_fernet()
    token_bytes = fernet.encrypt(text.encode("utf-8"))
    # token_bytes is already URL-safe base64; return as plain str for DB storage.
    return token_bytes.decode("utf-8")


def decrypt(token: str) -> str:
    """Decrypt a previously-encrypted token string and return the plaintext."""
    fernet = _get_fernet()
    try:
        plaintext_bytes = fernet.decrypt(token.encode("utf-8") if isinstance(token, str) else token)
        return plaintext_bytes.decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Decryption failed — invalid token or wrong key") from exc
