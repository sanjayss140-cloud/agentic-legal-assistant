import os
import sys
from pathlib import Path

# Add project root to sys.path
sys_path_root = str(Path(__file__).resolve().parent.parent.parent)
if sys_path_root not in sys.path:
    sys.path.insert(0, sys_path_root)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from groq import Groq
from backend.app import config
from backend.api.router import router as api_router
from backend.security.middleware import SecurityHeadersMiddleware
from backend.logging.structured_logger import StructuredLoggingMiddleware
from backend.services.metrics import generate_prometheus_metrics
from backend.ingestion.async_worker import recover_stale_jobs
from fastapi import Response

app = FastAPI(
    title="Agentic Legal Assistant API",
    description="Agentic Legal Assistant where every fact and citation is verifiable.",
    version="0.1.0",
)

# Enforce security headers and structured logging
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(StructuredLoggingMiddleware)

async def _self_keep_alive_worker():
    """
    Continuous heartbeat loop: Sends an outbound HTTP request to the public URL
    every 7 minutes so Render's 15-minute inactivity timer never triggers sleep.
    """
    import asyncio, httpx
    # Wait 60s after startup before first ping
    await asyncio.sleep(60)
    public_url = os.environ.get("RENDER_EXTERNAL_URL", "https://ala.onrender.com")
    ping_url = f"{public_url.rstrip('/')}/ping"
    while True:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(ping_url, headers={"User-Agent": "ALA-KeepAlive-Heartbeat/1.0"})
                print(f"[Keep-Alive] Pinged {ping_url} -> {res.status_code}")
        except Exception as exc:
            print(f"[Keep-Alive] Ping note: {exc}")
        # 420 seconds = 7 minutes
        await asyncio.sleep(420)

@app.on_event("startup")
async def on_startup():
    recovered = recover_stale_jobs()
    if recovered > 0:
        print(f"[Agentic Legal Assistant Worker] Recovered {recovered} stale ingestion jobs.")
    import asyncio
    asyncio.create_task(_self_keep_alive_worker())

allowed_origins = os.getenv(
    "CORS_ORIGINS", 
    "*"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allowed_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Router
app.include_router(api_router, prefix="/api")

@app.get("/ping")
def ping():
    """Ultra-fast, zero-overhead endpoint for keep-alive pings to prevent Render sleep."""
    import time
    return {"status": "alive", "timestamp": time.time(), "app": "Agentic Legal Assistant"}

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "app": "Agentic Legal Assistant",
        "version": "0.1.0",
    }

@app.get("/metrics")
def get_metrics():
    """Prometheus exposition metrics endpoint."""
    content = generate_prometheus_metrics()
    return Response(content=content, media_type="text/plain; version=0.0.4")

@app.get("/llm-check")
def llm_check():
    if not config.GROQ_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="GROQ_API_KEY is not set in environment or .env file. Please add GROQ_API_KEY to .env.",
        )
    
    try:
        client = Groq(api_key=config.GROQ_API_KEY)
        model = config.GROQ_FAST_MODEL
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": "say OK"}
            ],
            temperature=0.0,
            max_tokens=20,
        )
        reply = completion.choices[0].message.content.strip()
        return {
            "status": "ok",
            "model": model,
            "prompt": "say OK",
            "reply": reply,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Groq API call failed: {str(e)}",
        )

# Serve frontend build if available
frontend_dist = Path(sys_path_root) / "frontend" / "dist"
if frontend_dist.exists():
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    
    @app.get("/")
    def serve_index():
        index_file = frontend_dist / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"status": "ok", "app": "Agentic Legal Assistant"}
    
    @app.get("/bg.jpg")
    def serve_bg():
        bg_file = frontend_dist / "bg.jpg"
        if bg_file.exists():
            return FileResponse(bg_file)
        raise HTTPException(status_code=404, detail="Background not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host=config.HOST, port=config.PORT, reload=True)
