from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..auth import get_current_user
from ..database import get_db
from ..models import Signal, User

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("")
def list_signals(
    unread_only: int = 0,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Signal).filter(Signal.user_id == user.id)
    if unread_only:
        q = q.filter(Signal.is_read == 0)
    items = q.order_by(Signal.created_at.desc()).limit(limit).all()
    return {"ok": True, "data": [schemas.SignalOut.model_validate(i).model_dump(mode="json") for i in items]}


@router.put("/{sig_id}/read")
def mark_read(sig_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sig = db.query(Signal).filter(Signal.id == sig_id, Signal.user_id == user.id).first()
    if not sig:
        raise HTTPException(404, "Not found")
    sig.is_read = 1
    db.commit()
    return {"ok": True, "data": None}


@router.put("/read-all")
def mark_all_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Signal).filter(Signal.user_id == user.id, Signal.is_read == 0).update({"is_read": 1})
    db.commit()
    return {"ok": True, "data": None}
