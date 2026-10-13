import os
import time
import secrets
import base64
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash
import bcrypt
import pyotp
from backend.app import config
from backend.ingestion.pipeline import get_db

ph = PasswordHasher()

JWT_SECRET = os.getenv("JWT_SECRET", "lexground_super_secret_pilot_key_2026_change_in_prod")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 900  # 15 minutes

# Abstract Email Service Interface
class EmailServiceInterface:
    def send_password_reset_email(self, to_email: str, reset_link: str) -> bool:
        raise NotImplementedError

class ConsoleEmailService(EmailServiceInterface):
    """Console fallback email service for development and private pilot."""
    def send_password_reset_email(self, to_email: str, reset_link: str) -> bool:
        print("\n" + "="*60)
        print(f"[CONSOLE EMAIL DISPATCH] To: {to_email}")
        print(f"Subject: Password Reset Request for LexGround")
        print(f"Reset Link: {reset_link}")
        print(f"Token valid for 1 hour.")
        print("="*60 + "\n")
        return True

email_service: EmailServiceInterface = ConsoleEmailService()

def hash_password(password: str) -> str:
    """Hash password using Argon2id with bcrypt compatibility fallback."""
    try:
        return ph.hash(password)
    except Exception:
        # Fallback to bcrypt
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against Argon2id or bcrypt hash."""
    if hashed_password.startswith("$argon2"):
        try:
            return ph.verify(hashed_password, plain_password)
        except (VerifyMismatchError, InvalidHash):
            return False
    elif hashed_password.startswith("$2b$") or hashed_password.startswith("$2a$"):
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except Exception:
            return False
    return False

def create_access_token(user_id: str, email: str, role: str, matter_id: Optional[str] = None) -> str:
    expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {
        "sub": user_id,
        "email": email,
        "role": role,
        "matter_id": matter_id,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc)
    }
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    expires_delta = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {
        "sub": user_id,
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(timezone.utc)
    }
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None

def init_auth_db():
    """Initializes tables for multi-tenant accounts, matters, and password resets."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE,
        password_hash TEXT,
        role TEXT DEFAULT 'lawyer',
        totp_secret TEXT,
        totp_enabled INTEGER DEFAULT 0,
        failed_login_attempts INTEGER DEFAULT 0,
        locked_until REAL DEFAULT 0,
        consent_given INTEGER DEFAULT 0,
        consent_timestamp REAL DEFAULT 0,
        mask_pii_enabled INTEGER DEFAULT 0,
        retention_days INTEGER DEFAULT 0,
        created_at REAL
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS matters (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        name TEXT,
        client_ref TEXT,
        notes TEXT,
        created_at REAL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS password_resets (
        token TEXT PRIMARY KEY,
        user_id TEXT,
        expires_at REAL,
        used INTEGER DEFAULT 0
    );
    """)
    conn.commit()
    conn.close()

init_auth_db()

def create_user(email: str, password: str, role: str = "lawyer") -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    email_clean = email.strip().lower()
    if len(password) < 8:
        return False, "Password must be at least 8 characters long", None
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email_clean,))
    if cursor.fetchone():
        conn.close()
        return False, "User with this email already exists", None

    user_id = f"user_{secrets.token_hex(8)}"
    p_hash = hash_password(password)
    now = time.time()

    cursor.execute("""
    INSERT INTO users (id, email, password_hash, role, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, (user_id, email_clean, p_hash, role, now))
    
    # Create a default matter for this user
    matter_id = f"matter_{secrets.token_hex(6)}"
    cursor.execute("""
    INSERT INTO matters (id, user_id, name, client_ref, notes, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (matter_id, user_id, "Default Matter", "GENERAL-01", "Primary case folder", now))

    conn.commit()
    cursor.execute("SELECT id, email, role, consent_given, mask_pii_enabled FROM users WHERE id = ?", (user_id,))
    row = dict(cursor.fetchone())
    conn.close()
    return True, "User registered successfully", row

def authenticate_user(email: str, password: str, totp_code: Optional[str] = None) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    email_clean = email.strip().lower()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, email, password_hash, role, totp_secret, totp_enabled, failed_login_attempts, locked_until, consent_given, mask_pii_enabled 
    FROM users 
    WHERE email = ?
    """, (email_clean,))
    row = cursor.fetchone()
    now = time.time()

    if not row:
        conn.close()
        return False, "Invalid email or password", None

    user = dict(row)

    # Check Lockout
    if user["locked_until"] and user["locked_until"] > now:
        remaining = int(user["locked_until"] - now)
        conn.close()
        return False, f"Account temporarily locked due to failed attempts. Try again in {remaining} seconds.", None

    # Check Password
    if not verify_password(password, user["password_hash"]):
        new_attempts = user["failed_login_attempts"] + 1
        lock_until = now + LOCKOUT_DURATION_SECONDS if new_attempts >= MAX_FAILED_ATTEMPTS else 0
        cursor.execute("UPDATE users SET failed_login_attempts = ?, locked_until = ? WHERE id = ?", (new_attempts, lock_until, user["id"]))
        conn.commit()
        conn.close()
        if lock_until:
            return False, "Account locked due to 5 failed attempts. Please wait 15 minutes or reset password.", None
        return False, "Invalid email or password", None

    # Check 2FA if enabled
    if user["totp_enabled"] and user["totp_secret"]:
        if not totp_code:
            conn.close()
            return False, "2FA_REQUIRED", {"user_id": user["id"], "email": user["email"]}
        totp = pyotp.TOTP(user["totp_secret"])
        if not totp.verify(totp_code.strip()):
            conn.close()
            return False, "Invalid two-factor authentication code", None

    # Reset failed attempts
    cursor.execute("UPDATE users SET failed_login_attempts = 0, locked_until = 0 WHERE id = ?", (user["id"],))
    conn.commit()
    conn.close()

    return True, "Authentication successful", user

def setup_totp(user_id: str) -> Tuple[str, str]:
    """Generates a TOTP secret and provisioning URI for Google Authenticator / Authy."""
    secret = pyotp.random_base32()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    email = row["email"] if row else "lawyer"
    cursor.execute("UPDATE users SET totp_secret = ? WHERE id = ?", (secret, user_id))
    conn.commit()
    conn.close()
    
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=email, issuer_name="LexGround Legal")
    return secret, uri

def confirm_totp(user_id: str, code: str) -> bool:
    """Confirms TOTP code and marks 2FA enabled."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT totp_secret FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    if not row or not row["totp_secret"]:
        conn.close()
        return False
    
    totp = pyotp.TOTP(row["totp_secret"])
    if totp.verify(code.strip()):
        cursor.execute("UPDATE users SET totp_enabled = 1 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def initiate_password_reset(email: str, base_url: str = "http://localhost:8000") -> bool:
    email_clean = email.strip().lower()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email_clean,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return True # Prevent user enumeration

    user_id = row["id"]
    token = secrets.token_urlsafe(32)
    expires_at = time.time() + 3600 # 1 hour
    cursor.execute("INSERT INTO password_resets (token, user_id, expires_at) VALUES (?, ?, ?)", (token, user_id, expires_at))
    conn.commit()
    conn.close()

    reset_link = f"{base_url}/reset-password?token={token}"
    email_service.send_password_reset_email(email_clean, reset_link)
    return True

def complete_password_reset(token: str, new_password: str) -> Tuple[bool, str]:
    if len(new_password) < 8:
        return False, "Password must be at least 8 characters long"
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, expires_at, used FROM password_resets WHERE token = ?", (token,))
    row = cursor.fetchone()
    now = time.time()

    if not row or row["used"] == 1 or row["expires_at"] < now:
        conn.close()
        return False, "Reset token is invalid or expired"

    user_id = row["user_id"]
    new_hash = hash_password(new_password)
    cursor.execute("UPDATE users SET password_hash = ?, failed_login_attempts = 0, locked_until = 0 WHERE id = ?", (new_hash, user_id))
    cursor.execute("UPDATE password_resets SET used = 1 WHERE token = ?", (token,))
    conn.commit()
    conn.close()
    return True, "Password has been successfully reset"
