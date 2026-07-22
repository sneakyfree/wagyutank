from pathlib import Path

from fastapi import Body, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .config import settings
from .db import Base, engine, get_db
from .routers import (
    admin, ads, aggregated, animals, auth, catalog, claim, config as config_router, discussions,
    events, facilities, listings,
    canon, directory, feeding, help, market, news, newsletter, orders, payments, sale_events, sales, search, users, videos, wantads, zenkyo,
)

app = FastAPI(
    title="WagyuTank API",
    description="The world's marketplace for frozen Wagyu genetics — semen, embryos, and cloning rights.",
    version="0.1.0",
)

# CORS origins are derived from THIS tank's own domain, so every clone allows its
# own frontend (and any Cloudflare Pages preview) with no per-tank code change.
from . import tank as _tank
_tank_domain = _tank.brand().get("domain", "wagyutank.com")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_origin,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        f"https://www.{_tank_domain}",
        f"https://{_tank_domain}",
    ],
    # Any Cloudflare Pages production/preview subdomain (this tank's project).
    allow_origin_regex=r"https://[a-z0-9-]+(\.[a-z0-9-]+)?\.pages\.dev",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


app.include_router(auth.router)
app.include_router(newsletter.router)
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
app.include_router(sale_events.upcoming_router)
app.include_router(orders.router)
app.include_router(catalog.router)
app.include_router(videos.router)
app.include_router(zenkyo.router)
app.include_router(canon.router)
app.include_router(feeding.router)
app.include_router(help.router)
app.include_router(directory.router)
app.include_router(claim.router)
app.include_router(config_router.router)
app.include_router(wantads.router)

# Per-tank media (audio recordings etc.). Served from the API rather than the
# static frontend because Cloudflare Pages does not honor HTTP Range requests,
# which breaks seeking/progressive playback for long recordings; Starlette
# serves ranges properly and Cloudflare passes them through for proxied origins.
_media_dir = Path(__file__).resolve().parent.parent.parent / "tanks" / _tank.key() / "media"
if _media_dir.is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/media", StaticFiles(directory=str(_media_dir)), name="media")


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "wagyutank", "platform_fee_bps": settings.platform_fee_bps}


@app.get("/api/content/breed-history", tags=["content"])
def breed_history(lang: str = "en", db: Session = Depends(get_db)):
    from . import tank
    path = tank.seed_path("breed_history.md")
    md = path.read_text() if path.exists() else ""
    if lang and lang != "en" and md:
        from .services import translate
        md = translate.translate(db, md, lang, is_markdown=True)
    return {"markdown": md, "lang": lang}


@app.post("/api/translate", tags=["content"])
def translate_content(text: str = Body(..., embed=True), lang: str = Body("es"),
                      db: Session = Depends(get_db)):
    """Translate a block of our own content (cached). Length-capped. The
    `translated` flag lets the client distinguish a real translation from the
    English fallback (so it can retry/label instead of showing stale text)."""
    from .services import translate
    if len(text) > 12000:
        text = text[:12000]
    out, ok = translate.translate_one(db, text, lang)
    return {"text": out, "lang": lang, "translated": ok}


@app.post("/api/translate/batch", tags=["content"])
def translate_batch_content(items: list[dict] = Body(...), lang: str = Body("es"),
                            db: Session = Depends(get_db)):
    """Translate many short strings (headlines) in one call. items=[{id,text}].
    Returns {translations: {id: text}} for the ones that actually translated."""
    from .services import translate
    items = (items or [])[:60]
    return {"translations": translate.translate_batch(db, items, lang), "lang": lang}
