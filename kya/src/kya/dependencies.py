"""FastAPI dependency injection."""
from __future__ import annotations

import os
from functools import lru_cache

from .config import settings
from .utils.crypto import generate_ed25519_keypair


@lru_cache()
def get_platform_keys() -> tuple[str, str]:
    """Get or generate platform Ed25519 keys. Returns (public_pem, private_pem)."""
    pub_path = settings.JWT_PUBLIC_KEY_PATH
    priv_path = settings.JWT_PRIVATE_KEY_PATH

    if os.path.exists(pub_path) and os.path.exists(priv_path):
        with open(pub_path) as f:
            public_key = f.read()
        with open(priv_path) as f:
            private_key = f.read()
        return public_key, private_key

    # Generate new keys
    public_key, private_key = generate_ed25519_keypair()
    os.makedirs(os.path.dirname(pub_path), exist_ok=True)
    with open(pub_path, "w") as f:
        f.write(public_key)
    with open(priv_path, "w") as f:
        f.write(private_key)

    return public_key, private_key
