import os

import uvicorn

if __name__ == "__main__":
    reload_enabled = str(os.environ.get("UVICORN_RELOAD", "")).strip().lower() in {"1", "true", "yes", "on"}
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=reload_enabled,
        reload_dirs=["app"] if reload_enabled else None,
    )
