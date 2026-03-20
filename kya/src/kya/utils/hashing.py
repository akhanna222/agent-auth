"""SHA-256 and HMAC utilities."""
import hashlib
import hmac


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def hmac_sha256(key: str, message: str) -> str:
    return hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()
