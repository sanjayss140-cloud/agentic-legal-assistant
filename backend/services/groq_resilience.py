import time
import os
from typing import Dict, Any, Optional, List, Callable

class CircuitBreakerOpenError(Exception):
    """Raised when the circuit breaker trips due to repeated upstream failures."""
    def __init__(self, message: str = "LLM provider temporarily unavailable; cached verification is active"):
        super().__init__(message)
        self.message = message

class GroqCircuitBreaker:
    """
    Circuit breaker pattern tracking upstream Groq API health:
    - CLOSED: Normal operation.
    - OPEN: Tripped after failure_threshold consecutive failures; all calls fail-fast with clean message.
    - HALF_OPEN: After recovery_timeout, allows a canary request to test provider recovery.
    """
    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.state = "CLOSED"
        self.last_failure_time = 0.0

    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            self.state = "OPEN"

    def record_success(self):
        self.failures = 0
        self.state = "CLOSED"

    def can_attempt(self) -> bool:
        if self.state == "CLOSED":
            return True
        elif self.state == "OPEN":
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = "HALF_OPEN"
                return True
            return False
        elif self.state == "HALF_OPEN":
            return True
        return False

    def reset(self):
        self.failures = 0
        self.state = "CLOSED"
        self.last_failure_time = 0.0

# Singleton circuit breaker instance
global_circuit_breaker = GroqCircuitBreaker()

def resilient_groq_completion(
    groq_client: Any,
    messages: List[Dict[str, str]],
    model: str = "llama-3.3-70b-versatile",
    fallback_model: str = "llama-3.1-8b-instant",
    temperature: float = 0.1,
    max_tokens: int = 1024,
    circuit_breaker: Optional[GroqCircuitBreaker] = None,
    max_retries: int = 3,
    **kwargs
) -> Any:
    """
    Resilient invocation of Groq chat completions with:
    1. Circuit breaker trip and fail-fast fallback
    2. Exponential backoff on HTTP 429/503
    3. Automatic fallback from 70B to 8B model if 70B is rate-limited
    """
    cb = circuit_breaker or global_circuit_breaker

    if not cb.can_attempt():
        raise CircuitBreakerOpenError("LLM provider temporarily unavailable; cached verification is active")

    current_model = model
    last_err = None

    for attempt in range(max_retries):
        try:
            resp = groq_client.chat.completions.create(
                model=current_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            cb.record_success()
            return resp
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            is_rate_limit = "429" in err_str or "rate_limit" in err_str or "too many requests" in err_str
            is_service_down = "503" in err_str or "service unavailable" in err_str or "internal server error" in err_str or "500" in err_str

            if is_rate_limit or is_service_down:
                # Fallback to smaller model if primary was 70B
                if current_model == model and fallback_model != model:
                    current_model = fallback_model

                if attempt < max_retries - 1:
                    backoff = 0.1 * (2 ** attempt)
                    time.sleep(backoff)
                    continue

    # All retries exhausted
    cb.record_failure()
    if cb.state == "OPEN":
        raise CircuitBreakerOpenError("LLM provider temporarily unavailable; cached verification is active")
    raise last_err
