"""
Continual Learning Conversational AI - Backend Entry Point

Run with: uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import httpx

from core.config import settings
from core.database import engine, Base, get_db
from models.schemas import CustomerProfileResponse, ModeRequest, ExperimentRequest
from routes.chat import router as chat_router

# Create all database tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Continual Learning Conversational AI",
    description="A conversational AI system with continual learning capabilities",
    version="0.1.0",
)

# Allow frontend (localhost:3000) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(chat_router)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "message": "Continual Learning AI API is running"}


@app.get("/health")
async def health_check():
    """Advanced health check endpoint that also verifies LLM configuration and reachability."""
    status = {
        "status": "ok",
        "provider": settings.LLM_PROVIDER,
        "active_mode": settings.LLM_MODE,
        "active_model": settings.active_model,
        "ollama_reachable": False,
        "fast_model_exists": False,
        "quality_model_exists": False,
        "experiments": {
            "enable_memory": settings.ENABLE_MEMORY,
            "enable_recent_context": settings.ENABLE_RECENT_CONTEXT
        }
    }

    if status["provider"] == "ollama":
        base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                # 1. Check if Ollama is reachable
                res = await client.get(base_url)
                if res.status_code == 200:
                    status["ollama_reachable"] = True
                
                # 2. Check if the configured models are installed
                if status["ollama_reachable"]:
                    tags_res = await client.get(f"{base_url}/api/tags")
                    if tags_res.status_code == 200:
                        tags_data = tags_res.json()
                        models = [m.get("name") for m in tags_data.get("models", [])]
                        
                        f_model = settings.OLLAMA_FAST_MODEL
                        q_model = settings.OLLAMA_QUALITY_MODEL
                        
                        if f_model in models or f"{f_model}:latest" in models:
                            status["fast_model_exists"] = True
                        if q_model in models or f"{q_model}:latest" in models:
                            status["quality_model_exists"] = True
                            
        except Exception as e:
            print(f"[Health Check] Could not reach Ollama at {base_url}: {e}")

    return status

@app.post("/config/mode")
async def change_mode(request: ModeRequest):
    """Runtime override to toggle LLM modes."""
    settings.LLM_MODE = request.mode
    return {"status": "ok", "active_mode": settings.LLM_MODE, "active_model": settings.active_model}

@app.post("/config/experiment")
async def change_experiment(request: ExperimentRequest):
    """Runtime override to toggle experiment features."""
    settings.ENABLE_MEMORY = request.enable_memory
    settings.ENABLE_RECENT_CONTEXT = request.enable_recent_context
    return {"status": "ok", "experiments": {"enable_memory": settings.ENABLE_MEMORY, "enable_recent_context": settings.ENABLE_RECENT_CONTEXT}}

@app.get("/customer-profile/{session_id}", response_model=CustomerProfileResponse)
async def get_customer_profile(session_id: str, db: Session = Depends(get_db)):
    """Fetch structured memory context for a given session."""
    from models.database_models import CustomerProfile
    
    profile = db.query(CustomerProfile).filter(CustomerProfile.session_id == session_id).first()
    
    if profile:
        return CustomerProfileResponse(
            session_id=profile.session_id,
            name=profile.name or "Unknown",
            budget=profile.budget or "Not specified",
            preferred_category=profile.preferred_category or "Not specified",
            preferred_color=profile.preferred_color or "Not specified",
            priorities=profile.priorities or "Not specified",
            dislikes=profile.dislikes or "Not specified",
            updated_at=profile.updated_at.isoformat() if profile.updated_at else "Unknown"
        )
    
    return CustomerProfileResponse(
        session_id=session_id,
        name="Unknown",
        budget="Not specified",
        preferred_category="Not specified",
        preferred_color="Not specified",
        priorities="Not specified",
        dislikes="Not specified",
        updated_at="Never"
    )
