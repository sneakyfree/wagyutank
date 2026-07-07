from pathlib import Path

from fastapi import Body, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .config import settings
from .db import Base, engine, get_db
from .routers import (
    admin, ads, aggregated, animals, auth, discussions, events, facilities, listings,
    market, news, orders, payments, sale_events, sales, search, users,
)

app = FastAPI(
    title="WagyuTank API",
    description="The world's marketplace for frozen Wagyu genetics — semen, embryos, and cloning rights.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_origin,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://www.wagyutank.com",
        "https://wagyutank.com",
    ],
    # Cloudflare Pages production + preview deploys (wagyutank.pages.dev, <hash>.wagyutank.pages.dev)
    allow_origin_regex=r"https://([a-z0-9-]+\.)?wagyutank\.pages\.dev",
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
app.include_router(payments.router)
app.include_router(aggregated.router)
app.include_router(ads.router)
app.include_router(admin.router)
app.include_router(events.router)
app.include_router(discussions.router)
app.include_router(news.router)
app.include_router(market.router)
app.include_router(sales.router)
app.include_router(sale_events.router)
app.include_router(orders.router)


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "wagyutank", "platform_fee_bps": settings.platform_fee_bps}


@app.get("/api/content/breed-history", tags=["content"])
def breed_history(lang: str = "en", db: Session = Depends(get_db)):
    path = Path(__file__).parent / "seed" / "data" / "breed_history.md"
    md = path.read_text() if path.exists() else ""
    if lang and lang != "en" and md:
        from .services import translate
        md = translate.translate(db, md, lang, is_markdown=True)
    return {"markdown": md, "lang": lang}


@app.post("/api/translate", tags=["content"])
def translate_content(text: str = Body(..., embed=True), lang: str = Body("es"),
                      db: Session = Depends(get_db)):
    """Translate a block of our own content (cached). Length-capped."""
    from .services import translate
    if len(text) > 12000:
        text = text[:12000]
    return {"text": translate.translate(db, text, lang), "lang": lang}
