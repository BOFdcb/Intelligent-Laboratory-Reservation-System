from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Laboratory, Equipment, User
from ..schemas import (
    LaboratoryCreate, LaboratoryUpdate, LaboratoryOut,
    EquipmentCreate, EquipmentUpdate, EquipmentOut, ok,
)
from ..security import get_current_user, require_admin

router = APIRouter(prefix="/api", tags=["实验室与设备"])


# ---- 实验室 ----
@router.get("/labs")
def list_labs(page: int = 1, size: int = 20, keyword: str = "",
              db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    q = db.query(Laboratory).order_by(Laboratory.id)
    if keyword:
        q = q.filter(Laboratory.name.like(f"%{keyword}%"))
    total = q.count()
    items = q.offset((page - 1) * size).limit(size).all()
    return ok({
        "items": [LaboratoryOut.model_validate(l).model_dump(mode="json") for l in items],
        "total": total, "page": page, "size": size,
    })


@router.get("/labs/{lab_id}")
def get_lab(lab_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    lab = db.query(Laboratory).filter(Laboratory.id == lab_id).first()
    if not lab:
        raise HTTPException(status_code=404, detail="实验室不存在")
    data = LaboratoryOut.model_validate(lab).model_dump(mode="json")
    data["equipment"] = [EquipmentOut.model_validate(e).model_dump(mode="json") for e in lab.equipment]
    return ok(data)


@router.post("/labs")
def create_lab(payload: LaboratoryCreate, db: Session = Depends(get_db),
               _: User = Depends(require_admin)):
    lab = Laboratory(**payload.model_dump())
    db.add(lab)
    db.commit()
    db.refresh(lab)
    return ok(LaboratoryOut.model_validate(lab).model_dump(mode="json"), "创建成功")


@router.put("/labs/{lab_id}")
def update_lab(lab_id: int, payload: LaboratoryUpdate, db: Session = Depends(get_db),
               _: User = Depends(require_admin)):
    lab = db.query(Laboratory).filter(Laboratory.id == lab_id).first()
    if not lab:
        raise HTTPException(status_code=404, detail="实验室不存在")
    for k, v in payload.model_dump().items():
        setattr(lab, k, v)
    db.commit()
    db.refresh(lab)
    return ok(LaboratoryOut.model_validate(lab).model_dump(mode="json"), "更新成功")


@router.delete("/labs/{lab_id}")
def delete_lab(lab_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    lab = db.query(Laboratory).filter(Laboratory.id == lab_id).first()
    if not lab:
        raise HTTPException(status_code=404, detail="实验室不存在")
    db.delete(lab)
    db.commit()
    return ok(None, "删除成功")


# ---- 设备 ----
@router.get("/labs/{lab_id}/equipment")
def list_equipment(lab_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    items = db.query(Equipment).filter(Equipment.lab_id == lab_id).order_by(Equipment.id).all()
    return ok([EquipmentOut.model_validate(e).model_dump(mode="json") for e in items])


@router.post("/labs/{lab_id}/equipment")
def create_equipment(lab_id: int, payload: EquipmentCreate, db: Session = Depends(get_db),
                     _: User = Depends(require_admin)):
    lab = db.query(Laboratory).filter(Laboratory.id == lab_id).first()
    if not lab:
        raise HTTPException(status_code=404, detail="实验室不存在")
    equip = Equipment(lab_id=lab_id, **payload.model_dump())
    db.add(equip)
    db.commit()
    db.refresh(equip)
    return ok(EquipmentOut.model_validate(equip).model_dump(mode="json"), "创建成功")


@router.put("/equipment/{equip_id}")
def update_equipment(equip_id: int, payload: EquipmentUpdate, db: Session = Depends(get_db),
                     _: User = Depends(require_admin)):
    equip = db.query(Equipment).filter(Equipment.id == equip_id).first()
    if not equip:
        raise HTTPException(status_code=404, detail="设备不存在")
    for k, v in payload.model_dump().items():
        setattr(equip, k, v)
    db.commit()
    db.refresh(equip)
    return ok(EquipmentOut.model_validate(equip).model_dump(mode="json"), "更新成功")


@router.delete("/equipment/{equip_id}")
def delete_equipment(equip_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    equip = db.query(Equipment).filter(Equipment.id == equip_id).first()
    if not equip:
        raise HTTPException(status_code=404, detail="设备不存在")
    db.delete(equip)
    db.commit()
    return ok(None, "删除成功")
