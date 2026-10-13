import os
import base64
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from backend.app import config

_fernet_instance = None

def get_encryption_key() -> bytes:
    key_env = os.getenv("ENCRYPTION_KEY")
    if key_env:
        # If 32-byte urlsafe base64, use directly; otherwise derive with PBKDF2
        try:
            k_bytes = key_env.encode("utf-8")
            if len(base64.urlsafe_b64decode(k_bytes)) == 32:
                return k_bytes
        except Exception:
            pass
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"lexground_salt_at_rest_2026",
            iterations=100_000,
        )
        return base64.urlsafe_b64encode(kdf.derive(key_env.encode("utf-8")))

    # Persistent local secret file
    secret_dir = Path(config.BASE_DIR) / "data" / "secrets"
    secret_dir.mkdir(parents=True, exist_ok=True)
    key_file = secret_dir / "encryption.key"
    if key_file.exists():
        return key_file.read_bytes().strip()
    
    new_key = Fernet.generate_key()
    key_file.write_bytes(new_key)
    return new_key

def get_fernet() -> Fernet:
    global _fernet_instance
    if _fernet_instance is None:
        key = get_encryption_key()
        _fernet_instance = Fernet(key)
    return _fernet_instance

def encrypt_bytes(data: bytes) -> bytes:
    """Encrypt byte data at rest."""
    f = get_fernet()
    return f.encrypt(data)

def decrypt_bytes(encrypted_data: bytes) -> bytes:
    """Decrypt byte data from storage."""
    f = get_fernet()
    return f.decrypt(encrypted_data)
