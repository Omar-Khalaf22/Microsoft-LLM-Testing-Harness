"""Opt-in provisional API. Mount with create_app; existing /runs stays untouched."""

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request

from .executor import ReservedExecutor
from .models import ExecuteSuite, ExecuteVersion, Execution, Run
from .storage import Conflict

router = APIRouter(prefix="/prototype3", tags=["prototype3-provisional"])


def runtime(request: Request) -> ReservedExecutor:
    executor = getattr(request.app.state, "reserved_executor", None)
    if executor is None:
        raise HTTPException(
            503,
            detail={
                "code": "storage_unconfigured",
                "message": "Reservation adapter is not configured.",
            },
        )
    return executor


def guarded(operation):
    try:
        return operation()
    except HTTPException:
        raise
    except LookupError:
        raise HTTPException(
            404, detail={"code": "not_found", "message": "Record not found."}
        ) from None
    except Conflict:
        raise HTTPException(
            409, detail={"code": "run_conflict", "message": "Run is already claimed or finished."}
        ) from None
    except NotImplementedError:
        raise HTTPException(
            501, detail={"code": "unsupported", "message": "Storage operation not available."}
        ) from None
    except ValueError:
        raise HTTPException(
            422,
            detail={"code": "invalid_configuration", "message": "Saved configuration is invalid."},
        ) from None
    except Exception:
        raise HTTPException(
            503, detail={"code": "storage_failure", "message": "Execution could not be persisted."}
        ) from None


@router.post("/executions/test", response_model=Execution, status_code=201)
def reserve_test(body: ExecuteVersion, executor=Depends(runtime)):
    return guarded(
        lambda: executor.storage.reserve_test(body.test_id, body.test_version, body.rerun_of)
    )


@router.post("/executions/suite", response_model=Execution, status_code=201)
def reserve_suite(body: ExecuteSuite, executor=Depends(runtime)):
    return guarded(lambda: executor.storage.reserve_suite(body.suite_id))


@router.get("/executions/{execution_id}", response_model=Execution)
def get_execution(execution_id: str, executor=Depends(runtime)):
    return guarded(lambda: executor.storage.execution(execution_id))


@router.post("/runs/{run_id}/execute", response_model=Run)
def execute(run_id: str, executor=Depends(runtime)):
    return guarded(lambda: executor.execute(run_id))


@router.get("/runs/{run_id}", response_model=Run)
def get_run(run_id: str, executor=Depends(runtime)):
    return guarded(lambda: executor.storage.get(run_id))


def create_app(executor: ReservedExecutor | None = None) -> FastAPI:
    app = FastAPI(title="Prototype 3 provisional execution API")
    app.state.reserved_executor = executor
    app.include_router(router)
    return app
