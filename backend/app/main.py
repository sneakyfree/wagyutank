from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import Base, engine
from .routers import animals, auth, facilities, listings, search, users

app = FastAPI(
    title="WagyuTank API",
    description="The world's marketplace for frozen Wagyu genetics — semen, embryos, and cloning rights.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(animals.router)
app.include_router(facilities.router)
app.include_router(listings.router)
app.include_router(search.router)


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "wagyutank", "platform_fee_bps": settings.platform_fee_bps}


@app.get("/api/content/breed-history", tags=["content"])
def breed_history():
    path = Path(__file__).parent / "seed" / "data" / "breed_history.md"
    return {"markdown": path.read_text() if path.exists() else ""}
