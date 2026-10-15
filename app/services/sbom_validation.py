import json
import re
from dataclasses import dataclass
from typing import Any

from cyclonedx.schema import SchemaVersion
from cyclonedx.validation.json import JsonValidator

from app.errors import ApiError

# Provisional (docs/decisions.md): accepted CycloneDX spec versions.
SUPPORTED_SPEC_VERSIONS: dict[str, SchemaVersion] = {
    "1.4": SchemaVersion.V1_4,
    "1.5": SchemaVersion.V1_5,
    "1.6": SchemaVersion.V1_6,
}

_validators = {v: JsonValidator(sv) for v, sv in SUPPORTED_SPEC_VERSIONS.items()}
_REQUIRED_RE = re.compile(r"'([^']+)' is a required property")


@dataclass(frozen=True)
class ParsedComponent:
    name: str
    version: str
    purl: str | None


def _invalid_json(message: str) -> ApiError:
    return ApiError(400, "INVALID_JSON", message)


def _invalid_sbom(message: str) -> ApiError:
    return ApiError(400, "INVALID_SBOM", message)


def _location(path: list[Any]) -> str:
    out = ""
    for part in path:
        out += f"[{part}]" if isinstance(part, int) else f".{part}"
    return out.lstrip(".")


def parse_and_validate(raw: bytes) -> list[ParsedComponent]:
    """Fully validate a CycloneDX JSON document; raise ApiError(400) naming the reason."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _invalid_json("request body is not valid UTF-8 text") from exc
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _invalid_json(
            f"request body is not valid JSON: {exc.msg} (line {exc.lineno})"
        ) from exc
    if not isinstance(doc, dict):
        raise _invalid_sbom("CycloneDX document must be a JSON object")

    for field in ("bomFormat", "specVersion"):
        if field not in doc:
            raise _invalid_sbom(f"missing required field: {field}")
    if doc["bomFormat"] != "CycloneDX":
        raise _invalid_sbom(f"bomFormat must be 'CycloneDX', got {doc['bomFormat']!r}")
    spec = doc["specVersion"]
    if not isinstance(spec, str) or spec not in SUPPORTED_SPEC_VERSIONS:
        supported = ", ".join(SUPPORTED_SPEC_VERSIONS)
        raise _invalid_sbom(f"unsupported specVersion {spec!r}; supported versions: {supported}")

    err = _validators[spec].validate_str(text)
    if err is not None:
        data = err.data
        where = _location(list(data.path))
        match = _REQUIRED_RE.search(data.message)
        if match:
            prefix = f" in {where}" if where else ""
            raise _invalid_sbom(f"missing required field: {match.group(1)}{prefix}")
        raise _invalid_sbom(f"{where}: {data.message}" if where else data.message)

    components: list[ParsedComponent] = []
    for i, comp in enumerate(doc.get("components", [])):
        name = comp["name"]
        version = comp.get("version")
        # Provisional: the contract's Component requires a version, so reject the whole SBOM.
        if not isinstance(version, str) or not version.strip():
            raise _invalid_sbom(f"components[{i}] ({name!r}) is missing required field: version")
        purl = comp.get("purl")
        components.append(ParsedComponent(name, version, purl if isinstance(purl, str) else None))
    return components
