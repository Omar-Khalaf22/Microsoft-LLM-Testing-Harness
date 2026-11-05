from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.storage.access import AccessContext, get_access
from app.storage.errors import Conflict, NotFound
from app.storage.transfer import EvidenceBundle, export_evidence, import_evidence

router = APIRouter(tags=["evidence"])


class ExportSelection(BaseModel):
    run_ids: list[str] = Field(min_length=1, max_length=5000)


@router.post("/evidence/export", response_model=EvidenceBundle)
def export_runs(
    body: ExportSelection,
    session: Annotated[Session, Depends(get_db)],
    access: Annotated[AccessContext, Depends(get_access)],
):
    try:
        return export_evidence(session, access, body.run_ids)
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("/evidence/import", status_code=201)
def import_runs(
    body: EvidenceBundle,
    session: Annotated[Session, Depends(get_db)],
    access: Annotated[AccessContext, Depends(get_access)],
):
    try:
        with session.begin():
            return import_evidence(session, access, body)
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from None
    except IntegrityError:
        raise HTTPException(409, "Evidence conflicts with existing records.") from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
