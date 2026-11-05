from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.storage.access import AccessContext, get_access
from app.storage.history import list_history_summaries

router = APIRouter(tags=["history"])


@router.get("/history/runs")
def history(
    session: Annotated[Session, Depends(get_db)],
    access: Annotated[AccessContext, Depends(get_access)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
):
    try:
        return list_history_summaries(session, access, limit=limit, cursor=cursor)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
