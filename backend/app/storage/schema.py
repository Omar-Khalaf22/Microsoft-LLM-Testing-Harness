"""Generate/check the transport-independent evidence schema from its validated model."""

import json
import sys
from pathlib import Path

from app.storage.transfer import EvidenceBundle


def main():
    destination = Path(__file__).parents[3] / "schemas" / "evidence-4.0.schema.json"
    schema = EvidenceBundle.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    content = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
    if "--check" in sys.argv:
        if destination.read_text(encoding="utf-8") != content:
            raise RuntimeError("Evidence schema differs from its model. Regenerate it.")
    else:
        destination.parent.mkdir(exist_ok=True)
        destination.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
