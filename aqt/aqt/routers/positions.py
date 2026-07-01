from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..auth import get_current_user
from ..database import get_db
from ..models import Position, User

router = APIRouter(prefix="/api/positions", tags=["positions"])


@router.get("")
def list_positions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(Position).filter(Position.user_id == user.id).all()
    return {"ok": True, "data": [schemas.PositionOut.model_validate(i).model_dump(mode="json") for i in items]}


@router.post("")
def create_position(req: schemas.PositionCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pos = Position(user_id=user.id, **req.model_dump())
    db.add(pos)
    db.commit()
    db.refresh(pos)
    return {"ok": True, "data": schemas.PositionOut.model_validate(pos).model_dump(mode="json")}


@router.put("/{pos_id}")
def update_position(
    pos_id: int,
    req: schemas.PositionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pos = db.query(Position).filter(Position.id == pos_id, Position.user_id == user.id).first()
    if not pos:
        raise HTTPException(404, "Not found")
    updates = req.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(pos, k, v)
    db.commit()
    db.refresh(pos)
    return {"ok": True, "data": schemas.PositionOut.model_validate(pos).model_dump(mode="json")}


@router.delete("/{pos_id}")
def delete_position(pos_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pos = db.query(Position).filter(Position.id == pos_id, Position.user_id == user.id).first()
    if not pos:
        raise HTTPException(404, "Not found")
    db.delete(pos)
    db.commit()
    return {"ok": True, "data": None}
