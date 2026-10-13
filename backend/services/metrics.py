import threading
from typing import Dict, Tuple, List
from backend.ingestion.pipeline import get_db

_lock = threading.Lock()
_request_counts: Dict[Tuple[str, str, int], int] = {}
_retrieval_durations: List[float] = []
_verification_counts: Dict[Tuple[str, str], int] = {}

HISTOGRAM_BUCKETS = [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]

def record_request_metric(method: str, path: str, status: int):
    """Increments HTTP request counter."""
    with _lock:
        key = (method.upper(), path, status)
        _request_counts[key] = _request_counts.get(key, 0) + 1

def record_retrieval_latency(duration_seconds: float):
    """Records retrieval execution time in seconds."""
    with _lock:
        _retrieval_durations.append(max(0.0, float(duration_seconds)))

def record_verification_metric(gate: str, status: str):
    """Records Gate A, B, or C verification outcome (pass / fail)."""
    with _lock:
        key = (gate.lower(), status.lower())
        _verification_counts[key] = _verification_counts.get(key, 0) + 1

def get_ingestion_queue_depth() -> int:
    """Calculates active queue depth from database."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
        SELECT COUNT(*) as depth FROM ingestion_jobs
        WHERE status IN ('queued', 'extracting', 'chunking', 'embedding', 'indexing')
        """)
        row = cursor.fetchone()
        depth = row["depth"] if row else 0
        conn.close()
        return depth
    except Exception:
        return 0

def generate_prometheus_metrics() -> str:
    """Renders all registered metrics in standard Prometheus text format."""
    lines: List[str] = []

    # 1. HTTP Requests Total
    lines.append("# HELP http_requests_total Total number of HTTP requests processed")
    lines.append("# TYPE http_requests_total counter")
    with _lock:
        for (method, path, status), count in sorted(_request_counts.items()):
            lines.append(f'http_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}')

    # 2. Retrieval Latency Histogram
    lines.append("# HELP retrieval_latency_seconds Latency of hybrid retrieval operations in seconds")
    lines.append("# TYPE retrieval_latency_seconds histogram")
    with _lock:
        durations = list(_retrieval_durations)
    
    total_count = len(durations)
    total_sum = sum(durations)
    for b in HISTOGRAM_BUCKETS:
        cumulative = sum(1 for d in durations if d <= b)
        lines.append(f'retrieval_latency_seconds_bucket{{le="{b}"}} {cumulative}')
    lines.append(f'retrieval_latency_seconds_bucket{{le="+Inf"}} {total_count}')
    lines.append(f'retrieval_latency_seconds_sum {total_sum:.4f}')
    lines.append(f'retrieval_latency_seconds_count {total_count}')

    # 3. Verification Outcomes Total
    lines.append("# HELP verification_outcomes_total Total number of claim verification outcomes")
    lines.append("# TYPE verification_outcomes_total counter")
    with _lock:
        for (gate, status), count in sorted(_verification_counts.items()):
            lines.append(f'verification_outcomes_total{{gate="{gate}",status="{status}"}} {count}')

    # 4. Ingestion Queue Depth
    queue_depth = get_ingestion_queue_depth()
    lines.append("# HELP ingestion_queue_depth Current number of ingestion jobs actively queued or processing")
    lines.append("# TYPE ingestion_queue_depth gauge")
    lines.append(f'ingestion_queue_depth {queue_depth}')

    return "\n".join(lines) + "\n"
