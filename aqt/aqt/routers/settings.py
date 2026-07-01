from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..auth import get_current_user
from ..database import get_db
from ..models import User

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings(user: User = Depends(get_current_user)):
    return {
        "ok": True,
        "data": {
            "email": user.email,
            "smtp_host": user.smtp_host,
            "smtp_port": user.smtp_port,
            "smtp_user": user.smtp_user,
        },
    }


@router.put("")
def update_settings(req: schemas.SettingsUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    updates = req.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(user, k, v)
    db.commit()
    return {"ok": True, "data": None}
