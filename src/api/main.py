from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routers import workflow, monitor, novels, prompts, approvals
from src.core.database import init_db
from src.core.container import init_container
from src.core.app_settings import get_settings, reload_settings
from src.core.config import Settings
from pathlib import Path

app = FastAPI(title="Prometheus Forge API", version="2.0.0")
app.state.config = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(workflow.router)
app.include_router(monitor.router)
app.include_router(novels.router)
app.include_router(prompts.router)
app.include_router(approvals.router)


@app.on_event("startup")
async def startup_event():
    await init_db()
    init_container()
    project_root = Path(__file__).parent.parent.parent
    app.state.config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")


@app.get("/")
async def root():
    return {"message": "Prometheus Forge API v2.0"}


@app.get("/health")
async def health():
    import redis
    from src.core.database import engine
    
    checks = {
        "api": "ok",
        "redis": "ok",
        "database": "ok"
    }
    
    try:
        r = redis.Redis(host=get_settings().redis_host, port=get_settings().redis_port)
        r.ping()
    except:
        checks["redis"] = "error"
    
    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
    except:
        checks["database"] = "error"
    
    status_code = 200 if all(v == "ok" for v in checks.values()) else 503
    return checks


@app.post("/admin/reload-config")
async def reload_config():
    from src.core.container import reload_settings as reload_container_settings
    
    project_root = Path(__file__).parent.parent.parent
    new_config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
    app.state.config = new_config
    
    reload_settings()
    reload_container_settings()
    
    return {"status": "reloaded", "config": {
        "model": new_config.model.name,
        "provider": new_config.model.provider
    }}
