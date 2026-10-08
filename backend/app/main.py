import os
import sys
from pathlib import Path

# Add project root to sys.path
sys_path_root = str(Path(__file__).resolve().parent.parent.parent)
if sys_path_root not in sys.path:
    sys.path.insert(0, sys_path_root)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
from backend.app import config

app = FastAPI(
    title="LexGround API",
    description="Agentic Legal Assistant where every fact and citation is verifiable.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {
        "app": "LexGround",
        "description": "Agentic Legal Assistant",
        "health_check": "/health",
        "llm_check": "/llm-check",
    }

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "app": "LexGround",
        "version": "0.1.0",
    }

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host=config.HOST, port=config.PORT, reload=True)
