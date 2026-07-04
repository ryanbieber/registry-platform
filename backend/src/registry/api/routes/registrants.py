from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from registry.db import get_session
from registry.schemas import RegistrantDetail, RegistrantListItem
from registry.services import get_registrant, list_registrants

router = APIRouter(prefix="/registrants", tags=["registrants"])


@router.get("", response_model=list[RegistrantListItem])
def registrants(session: Session = Depends(get_session)) -> list[RegistrantListItem]:
    return list_registrants(session)


@router.get("/{registrant_id}", response_model=RegistrantDetail)
def registrant_detail(registrant_id: str, session: Session = Depends(get_session)) -> RegistrantDetail:
    registrant = get_registrant(session, registrant_id)
    if registrant is None:
        raise HTTPException(status_code=404, detail="Registrant not found")
    return registrant
