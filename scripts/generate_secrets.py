#!/usr/bin/env python3
"""
Agentic Legal Assistant: Secret Generator
Generates cryptographically secure secrets for production deployment:
- JWT_SECRET (64-character hex)
- ENCRYPTION_KEY (Fernet AES-256 base64)
- POSTGRES_PASSWORD (256-bit safe URL token)
- REDIS_PASSWORD (256-bit safe URL token)
"""

import secrets
from pathlib import Path
from cryptography.fernet import Fernet

def generate_all_secrets():
    jwt_secret = secrets.token_hex(32)
    encryption_key = Fernet.generate_key().decode()
    postgres_password = secrets.token_urlsafe(24)
    redis_password = secrets.token_urlsafe(24)

    return {
        "JWT_SECRET": jwt_secret,
        "ENCRYPTION_KEY": encryption_key,
        "POSTGRES_PASSWORD": postgres_password,
        "REDIS_PASSWORD": redis_password,
    }

def print_or_write():
    sec = generate_all_secrets()
    print("=" * 60)
    print("Generated Production Secrets for LexGround Pilot Deployment")
    print("=" * 60)
    for k, v in sec.items():
        print(f"{k}={v}")
    print("=" * 60)
    print("Keep these values safe! Add them to your server's .env file.")
    print("Do NOT commit your populated .env to any public repository.")

if __name__ == "__main__":
    print_or_write()
