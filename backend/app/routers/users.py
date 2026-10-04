import os
import uuid

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import UserOut, UserUpdate, ok
from ..security import get_current_user, require_admin

router = APIRouter(prefix="/api/users", tags=["用户"])

UPLOAD_DIR = "uploads"
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return ok(UserOut.model_validate(current_user).model_dump(mode="json"))


@router.put("/me")
def update_me(payload: UserUpdate, db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)):
    if payload.nickname is not None:
        current_user.nickname = payload.nickname
    if payload.email is not None:
        current_user.email = payload.email
    db.commit()
    db.refresh(current_user)
    return ok(UserOut.model_validate(current_user).model_dump(mode="json"), "更新成功")


@router.post("/me/avatar")
async def upload_avatar(file: UploadFile = File(...), db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="仅支持图片文件")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_DIR, filename)
    content = await file.read()
    with open(path, "wb") as f:
        f.write(content)
    current_user.avatar = f"/uploads/{filename}"
    db.commit()
    return ok({"avatar": current_user.avatar}, "上传成功")


# ---- 管理员用户管理 ----
@router.get("")
def list_users(page: int = 1, size: int = 20, db: Session = Depends(get_db),
               _: User = Depends(require_admin)):
    q = db.query(User).order_by(User.id)
    total = q.count()
    items = q.offset((page - 1) * size).limit(size).all()
    return ok({
        "items": [UserOut.model_validate(u).model_dump(mode="json") for u in items],
        "total": total, "page": page, "size": size,
    })
