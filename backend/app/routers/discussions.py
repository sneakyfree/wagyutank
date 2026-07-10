"""Discussion threads — the translated global commons.

A comment written in any language is READ in whatever language the viewer has
selected: a Japanese breeder's comment appears in Portuguese to a Brazilian, in
German to a German. The original is always preserved and one tap away. Each
commenter carries their country flag. This is WagyuTank's moat: one worldwide
conversation, every reader in their own tongue."""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Comment, User
from ..security import get_current_user
from ..services import ratelimit
from ..services import translate as tr

router = APIRouter(tags=["discussions"])


def _out(c: Comment) -> dict:
    country = c.user.country if getattr(c, "user", None) else None
    return {"id": c.id, "author_handle": c.author_handle, "author_name": c.author_name,
            "body": c.body, "original_body": c.body, "source_lang": (c.lang or "en"),
            "translated": False, "country": country, "likes": c.likes, "is_seed": c.is_seed,
            "parent_id": c.parent_id, "created_at": c.created_at}


@router.get("/api/animals/{reg}/comments")
def list_comments(reg: str, lang: str = "en", db: Session = Depends(get_db)):
    rows = (db.query(Comment).filter(Comment.animal_reg == reg, Comment.status == "visible")
            .order_by(Comment.created_at.asc()).all())
    reader = (lang or "en").lower()

    # Batch-translate every comment whose source language differs from the
    # reader's — one LLM call for the whole thread (cached permanently after).
    to_translate = [{"id": c.id, "text": c.body} for c in rows
                    if (c.lang or "en") != reader and reader in tr.LANGS]
    translations = tr.translate_batch(db, to_translate, reader) if to_translate else {}

    nodes = {}
    for c in rows:
        d = _out(c)
        t = translations.get(c.id)
        if t:
            d["body"] = t
            d["translated"] = True
        nodes[c.id] = d

    by_parent: dict = {}
    for c in rows:
        by_parent.setdefault(c.parent_id, []).append(c)
    threads = []
    for top in by_parent.get(None, []):
        node = nodes[top.id]
        node["replies"] = [nodes[r.id] for r in by_parent.get(top.id, [])]
        threads.append(node)
    threads.sort(key=lambda t: t["created_at"], reverse=True)
    return {"count": len(rows), "threads": threads, "reader_lang": reader}


@router.post("/api/animals/{reg}/comments")
def add_comment(reg: str, body: str = Body(..., embed=True), parent_id: int | None = Body(None),
                lang: str | None = Body(None), user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    text = (body or "").strip()
    if not text:
        raise HTTPException(400, "Say something first.")
    if len(text) > 4000:
        raise HTTPException(400, "That's a bit long — keep it under 4000 characters.")
    if not ratelimit.allow(f"comment:{user.id}", 8, 300):
        raise HTTPException(429, "You're posting quickly — take a breather and try again.")
    src = (lang or "en").lower()
    if src not in tr.LANGS:
        src = "en"
    c = Comment(animal_reg=reg, user_id=user.id,
                author_handle=user.handle or user.display_name,
                author_name=user.display_name, body=text, lang=src,
                parent_id=parent_id, is_seed=False)
    db.add(c)
    db.commit()
    db.refresh(c)
    return _out(c)


@router.post("/api/comments/{comment_id}/like")
def like_comment(comment_id: int, db: Session = Depends(get_db)):
    c = db.get(Comment, comment_id)
    if not c:
        raise HTTPException(404, "Not found")
    c.likes += 1
    db.commit()
    return {"likes": c.likes}
