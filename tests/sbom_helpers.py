import json
from typing import Any


def make_sbom(n: int, spec: str = "1.6", prefix: str = "lib") -> dict[str, Any]:
    return {
        "bomFormat": "CycloneDX",
        "specVersion": spec,
        "version": 1,
        "components": [
            {
                "type": "library",
                "name": f"{prefix}-{i}",
                "version": f"{i}.0.0",
                "purl": f"pkg:npm/{prefix}-{i}@{i}.0.0",
            }
            for i in range(n)
        ],
    }


def raw(doc: Any) -> bytes:
    return json.dumps(doc).encode()
