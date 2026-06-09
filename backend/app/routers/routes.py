from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.train_route_service import get_train_route_state

router = APIRouter(tags=["routes"])


# ─── Endpoint ─────────────────────────────────────────────────────────────────
@router.get("/routes/train")
async def get_train_route(
    lat1: float = Query(...),
    lon1: float = Query(...),
    lat2: float = Query(...),
    lon2: float = Query(...),
    db: Session = Depends(get_db),
):
    geometry, status = get_train_route_state(db, lat1, lon1, lat2, lon2)
    return {"geometry": geometry, "status": status}
