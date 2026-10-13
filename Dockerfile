# ==============================================================================
# LexGround: Agentic Legal Assistant - Production Multi-Stage Container
# ==============================================================================

# Stage 1: Build & Package Python Backend & Assets
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ------------------------------------------------------------------------------
# Stage 2: Minimal, Hardened Runtime Image
# ------------------------------------------------------------------------------
FROM python:3.11-slim AS runner

# Security: Install only minimal runtime dependencies (OCR + poppler + curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-hin \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Security: Create non-root dedicated user
RUN groupadd -g 1001 lexground && \
    useradd -u 1001 -g lexground -m -s /bin/bash lexground

WORKDIR /app

# Copy installed python wheels from builder
COPY --from=builder /install /usr/local

# Copy application files
COPY alembic.ini .
COPY alembic ./alembic
COPY backend ./backend
COPY frontend ./frontend

# Create persistent storage directories with strict non-root ownership
RUN mkdir -p /app/data/corpus /app/data/secrets && \
    chown -R lexground:lexground /app

# Run as non-root user
USER lexground

# Environment defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATABASE_PATH=/app/data/lexground.db \
    CORPUS_DIR=/app/data/corpus \
    SECRETS_DIR=/app/data/secrets \
    PORT=8000 \
    HOST=0.0.0.0

EXPOSE 8000

# Container healthcheck querying API health
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

# Production startup command: run migrations then launch uvicorn
CMD ["sh", "-c", "python -m alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 2"]
