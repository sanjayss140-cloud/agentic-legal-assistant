import time
import json
import uuid
import sys
from datetime import datetime, timezone
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """
    Structured JSON HTTP Logger:
    Logs request_id, user_id, matter_id, latency, token count, and status code.
    Strictly excludes document text, prompts, and authentication secrets.
    """
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        start_time = time.time()

        # Extract context if present (without decrypting tokens or logging credentials)
        user_id = request.headers.get("x-user-id") or getattr(request.state, "user_id", None)
        matter_id = request.headers.get("x-matter-id") or getattr(request.state, "matter_id", None)

        # Call next middleware/route handler
        response: Response = await call_next(request)

        latency_ms = round((time.time() - start_time) * 1000, 2)
        token_count = getattr(request.state, "token_count", 0)

        # Build clean JSON record
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": "INFO" if response.status_code < 400 else "WARNING" if response.status_code < 500 else "ERROR",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "user_id": user_id,
            "matter_id": matter_id,
            "token_count": token_count
        }

        # Record Prometheus metric
        try:
            from backend.services.metrics import record_request_metric
            record_request_metric(request.method, request.url.path, response.status_code)
        except Exception:
            pass

        # Safe output without secret leaks
        sys.stdout.write(json.dumps(log_entry) + "\n")
        sys.stdout.flush()

        response.headers["X-Request-ID"] = request_id
        return response
