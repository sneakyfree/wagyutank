"""Discussion threads on foundation-animal media-center pages."""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Comment, User
from ..security import get_current_user
from ..services import ratelimit

router = APIRouter(tags=["discussions"])


def _out(c: Comment) -> dict:
    # Region flair: the commenter's country makes the global room feel global.
    country = c.user.country if getattr(c, "user", None) else None
    return {"id": c.id, "author_handle": c.author_handle, "author_name": c.author_name,
            "body": c.body, "likes": c.likes, "is_seed": c.is_seed, "country": country,
            "parent_id": c.parent_id, "created_at": c.created_at}


@router.get("/api/animals/{reg}/comments")
def list_comments(reg: str, db: Session = Depends(get_db)):
    rows = db.query(Comment).filter(Comment.animal_reg == reg, Comment.status == "visible") \
        .order_by(Comment.created_at.asc()).all()
    by_parent: dict = {}
    for c in rows:
        by_parent.setdefault(c.parent_id, []).append(c)
    threads = []
    for top in by_parent.get(None, []):
        node = _out(top)
        node["replies"] = [_out(r) for r in by_parent.get(top.id, [])]
        threads.append(node)
    threads.sort(key=lambda t: t["created_at"], reverse=True)
    return {"count": len(rows), "threads": threads}


@router.post("/api/animals/{reg}/comments")
def add_comment(reg: str, body: str = Body(..., embed=True), parent_id: int | None = Body(None),
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    text = (body or "").strip()
    if not text:
        raise HTTPException(400, "Say something first.")
    if len(text) > 4000:
        raise HTTPException(400, "That's a bit long — keep it under 4000 characters.")
    if not ratelimit.allow(f"comment:{user.id}", 8, 300):
        raise HTTPException(429, "You're posting quickly — take a breather and try again.")
    c = Comment(animal_reg=reg, user_id=user.id,
                author_handle=user.handle or user.display_name,
                author_name=user.display_name, body=text, parent_id=parent_id, is_seed=False)
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
