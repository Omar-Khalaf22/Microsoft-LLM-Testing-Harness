"""Authenticated evidence transfer, including environments without a browser login."""

import argparse
import json
import os
from pathlib import Path

from fastapi.security import HTTPAuthorizationCredentials

from app.database import SessionLocal
from app.storage.access import get_access
from app.storage.transfer import EvidenceBundle, export_evidence, import_evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("export", "import"))
    parser.add_argument("file", type=Path)
    parser.add_argument("--run-id", action="append", default=[])
    args = parser.parse_args()
    token = os.getenv("HARNESS_ACCESS_TOKEN")
    access = get_access(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=token) if token else None
    )
    if args.operation == "export":
        with SessionLocal() as session:
            bundle = export_evidence(session, access, args.run_id)
        # Refuse accidental evidence-file replacement.
        with args.file.open("x", encoding="utf-8") as output:
            output.write(bundle.model_dump_json(indent=2))
        print(f"Exported {len(bundle.runs)} runs.")
    else:
        bundle = EvidenceBundle.model_validate_json(args.file.read_text(encoding="utf-8"))
        with SessionLocal.begin() as session:
            result = import_evidence(session, access, bundle)
        print(json.dumps(result))


if __name__ == "__main__":
    main()
