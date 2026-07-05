from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from registry.db import get_session
from registry.enrichment import load_address_supporting_information, refresh_address_supporting_information
from registry.schemas import AddressRead
from registry.services import address_to_read

router = APIRouter(prefix="/addresses", tags=["addresses"])


@router.post("/{address_id}/enrich", response_model=AddressRead)
async def enrich_address(
    address_id: UUID,
    force: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> AddressRead:
    address = await refresh_address_supporting_information(session, address_id, force=force)
    if address is None:
        raise HTTPException(status_code=404, detail="Address not found")
    return address_to_read(address, load_address_supporting_information(session, address.id))
