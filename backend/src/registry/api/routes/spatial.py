from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from registry.db import get_session
from registry.schemas import IowaH3MapRead
from registry.spatial import get_iowa_h3_map

router = APIRouter(prefix="/spatial", tags=["spatial"])


@router.get("/iowa/h3", response_model=IowaH3MapRead)
def iowa_h3_map(
    resolution: int = Query(default=10, ge=0, le=10),
    session: Session = Depends(get_session),
) -> IowaH3MapRead:
    return get_iowa_h3_map(session, resolution=resolution)
