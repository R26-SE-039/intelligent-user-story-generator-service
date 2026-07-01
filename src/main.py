"""Main application entrypoint."""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.user_stories import router as user_stories_router
from src.api.routes.speech import router as speech_router

app = FastAPI(title="Intelligent User Story Generator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(speech_router, prefix="/speech")
app.include_router(user_stories_router, prefix="/pipeline")

@app.get("/health")
def health() -> dict[str, str]:
    """Simple service health endpoint."""
    return {"status": "ok", "service": "intelligent-user-story-generator"}

if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8001, reload=True)
