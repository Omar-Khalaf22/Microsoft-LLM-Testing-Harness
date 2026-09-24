import argparse
import json
from pathlib import Path
from typing import Any

from app.database import SessionLocal
from app.repositories import save_run_result


def load_result(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        result = json.load(file)

    if not isinstance(result, dict):
        raise ValueError("The run result must be a JSON object.")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import a structured LLM test run into PostgreSQL."
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Path to the structured run-result JSON file.",
    )
    arguments = parser.parse_args()

    result = load_result(arguments.path)

    with SessionLocal.begin() as session:
        run = save_run_result(session, result)

    print(f"Saved run {run.id}.")


if __name__ == "__main__":
    main()
