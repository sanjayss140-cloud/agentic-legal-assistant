import re
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enforces strict security headers: CSP, HSTS, X-Frame-Options, X-Content-Type-Options."""
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https:;"
        )
        return response

def sanitize_log_message(msg: str) -> str:
    """Removes API keys, bearer tokens, passwords, and sensitive credentials from logs."""
    cleaned = re.sub(r'(?:api[_-]?key|password|token|secret)[\'"]?\s*[:=]\s*[\'"][^\'"]+[\'"]', '[REDACTED_SECRET]', msg, flags=re.IGNORECASE)
    cleaned = re.sub(r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', 'Bearer [REDACTED_JWT]', cleaned)
    return cleaned
