"""
Prometheus Forge API - Scenario-Based Application

This is the new main entry point for the Prometheus Forge API.
It dynamically loads scenarios and registers their routes.

For backward compatibility, the old main.py is still available.
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

# Import core routers (generic, non-scenario-specific)
from src.api.routers import workflow, monitor, prompts, approvals, help as help_router, retrieval, inspector
from src.api.websocket import router as ws_router, start_broadcast_consumer
from src.core.database import init_db
from src.core.container import init_container
from src.core.app_settings import get_settings, reload_settings
from src.core.config import Settings

# Import scenario system
from src.core.scenario_registry import ScenarioRegistry

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Prometheus Forge API",
    version="3.0.0",
    description="Distributed Agentic Orchestration Engine with Multi-Scenario Support"
)

app.state.config = None
app.state.scenarios = {}

# CORS middleware
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


def register_scenario_routes():
    """
    Register routes from all loaded scenarios.

    This dynamically loads scenario routers and registers them with the app.
    """
    registry = ScenarioRegistry.get_instance()
    scenarios = registry.get_all_scenarios()

    for scenario_name, scenario in scenarios.items():
        logger.info(f"Loading scenario: {scenario_name} v{scenario.get_version()}")

        # Get routers from scenario
        routers = scenario.get_routers()

        for router in routers:
            # Register router with scenario prefix
            app.include_router(
                router,
                prefix=f"/scenarios/{scenario_name}",
                tags=[f"scenario:{scenario_name}"]
            )
            logger.info(f"  - Registered router: {router.prefix}")

        # Store scenario in app state
        app.state.scenarios[scenario_name] = scenario

    logger.info(f"Loaded {len(scenarios)} scenarios")


# Include generic routers (not scenario-specific)
app.include_router(workflow.router, tags=["workflow"])
app.include_router(monitor.router, tags=["monitor"])
app.include_router(prompts.router, tags=["prompts"])
app.include_router(approvals.router, tags=["approvals"])
app.include_router(help_router.router, tags=["help"])
app.include_router(retrieval.router, tags=["retrieval"])
app.include_router(inspector.router, tags=["inspector"])
app.include_router(ws_router, tags=["websocket"])


@app.on_event("startup")
async def startup_event():
    """
    Startup event handler.

    Initializes database, container, and loads scenarios.
    """
    logger.info("Starting Prometheus Forge API v3.0...")

    # Initialize database
    await init_db()

    # Initialize container (DI)
    init_container()

    # Start WebSocket broadcast consumer
    try:
        start_broadcast_consumer()
    except Exception as e:
        logger.warning(f"WebSocket broadcast consumer failed: {e}")

    # Load settings
    project_root = Path(__file__).parent.parent.parent
    app.state.config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")

    # Load scenarios
    # This imports scenarios which auto-register themselves
    try:
        import scenarios.novel  # Auto-registers novel scenario
        logger.info("Imported novel scenario")
    except Exception as e:
        logger.error(f"Failed to import novel scenario: {e}")

    # Register scenario routes
    register_scenario_routes()

    logger.info("Prometheus Forge API started successfully")


@app.get("/", tags=["root"])
async def root():
    """Root endpoint - API information"""
    return {
        "message": "Prometheus Forge API v3.0",
        "description": "Distributed Agentic Orchestration Engine",
        "scenarios": list(app.state.scenarios.keys()),
        "version": "3.0.0"
    }


@app.get("/health", tags=["health"])
async def health():
    """Health check endpoint"""
    import redis
    from src.core.database import engine

    checks = {
        "api": "ok",
        "redis": "ok",
        "database": "ok",
        "scenarios": len(app.state.scenarios)
    }

    # Check Redis
    try:
        r = redis.Redis(host=get_settings().redis_host, port=get_settings().redis_port)
        r.ping()
    except Exception as e:
        checks["redis"] = f"error: {str(e)}"

    # Check Database
    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
    except Exception as e:
        checks["database"] = f"error: {str(e)}"

    status_code = 200 if all(
        v == "ok" or isinstance(v, int)
        for v in checks.values()
    ) else 503

    return checks


@app.get("/scenarios", tags=["scenarios"])
async def list_scenarios():
    """
    List all loaded scenarios.

    Returns:
        Dictionary of scenario information
    """
    scenarios_info = {}

    for name, scenario in app.state.scenarios.items():
        scenarios_info[name] = {
            "name": scenario.get_name(),
            "version": scenario.get_version(),
            "description": scenario.get_description(),
            "agents": list(scenario.get_agents().keys()),
            "routers": len(scenario.get_routers())
        }

    return {
        "count": len(scenarios_info),
        "scenarios": scenarios_info
    }


@app.get("/scenarios/{scenario_name}", tags=["scenarios"])
async def get_scenario_info(scenario_name: str):
    """
    Get detailed information about a scenario.

    Args:
        scenario_name: Scenario name

    Returns:
        Scenario information
    """
    from fastapi import HTTPException

    scenario = app.state.scenarios.get(scenario_name)

    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_name}")

    return {
        "name": scenario.get_name(),
        "version": scenario.get_version(),
        "description": scenario.get_description(),
        "agents": scenario.get_agents(),
        "workflow": scenario.get_workflow_config() if hasattr(scenario, 'get_workflow_config') else {}
    }


@app.post("/admin/reload-config", tags=["admin"])
async def reload_config():
    """
    Reload configuration from file.

    Returns:
        Reload status
    """
    from src.core.container import reload_settings as reload_container_settings

    project_root = Path(__file__).parent.parent.parent
    new_config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
    app.state.config = new_config

    reload_settings()
    reload_container_settings()

    return {
        "status": "reloaded",
        "config": {
            "model": new_config.model.name,
            "provider": new_config.model.provider
        }
    }


@app.post("/admin/reload-scenarios", tags=["admin"])
async def reload_scenarios():
    """
    Reload all scenarios.

    Returns:
        Reload status
    """
    # Clear existing scenario routes would require app rebuild
    # For now, just log and return status
    logger.info("Scenario reload requested (requires app restart)")

    return {
        "status": "restart_required",
        "message": "Scenario reloading requires application restart",
        "current_scenarios": list(app.state.scenarios.keys())
    }


# For backward compatibility, also allow importing from main.py
__all__ = ["app"]
