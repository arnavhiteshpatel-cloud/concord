"""Export the event-envelope JSON Schema to contracts/ (run via `make schema`)."""

from __future__ import annotations

import json
from pathlib import Path

from brainos.contracts import envelope_json_schema

OUT = Path(__file__).resolve().parents[1] / "contracts" / "event-envelope.v1.schema.json"

if __name__ == "__main__":
    OUT.write_text(json.dumps(envelope_json_schema(), indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUT}")
