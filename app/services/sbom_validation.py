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


def _duplicate_message(where: str, items: list[Any]) -> str:
    """'<where> contains duplicate entries: <where>[i] repeats <where>[j]' for the first repeat."""
    seen: dict[str, int] = {}
    for i, item in enumerate(items):
        key = json.dumps(item, sort_keys=True)
        if key in seen:
            return f"{where} contains duplicate entries: {where}[{i}] repeats {where}[{seen[key]}]"
        seen[key] = i
    return f"{where} contains duplicate entries"


def parse_and_validate(raw: bytes) -> list[ParsedComponent]:
    """Fully validate a CycloneDX JSON document; raise ApiError(400) naming the reason."""
    try:
        return _parse(raw)
    except RecursionError as exc:
        # The JSON parser, the schema validator and _flatten all recurse once per nesting level,
        # so a document nested hundreds of levels deep (far beyond any real SBOM) exhausts
        # Python's stack. That is invalid input, not a server error.
        raise _invalid_sbom("CycloneDX document is nested too deeply to validate") from exc


def _parse(raw: bytes) -> list[ParsedComponent]:
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
        if data.validator == "uniqueItems" and isinstance(data.instance, list):
            # The raw message embeds the whole array (~37K characters for the fixture).
            raise _invalid_sbom(_duplicate_message(where, data.instance))
        match = _REQUIRED_RE.search(data.message)
        if match:
            prefix = f" in {where}" if where else ""
            raise _invalid_sbom(f"missing required field: {match.group(1)}{prefix}")
        raise _invalid_sbom(f"{where}: {data.message}" if where else data.message)

    components: list[ParsedComponent] = []
    _flatten(doc.get("components", []), "components", components)
    return components


def _flatten(items: list[Any], path: str, out: list[ParsedComponent]) -> None:
    """Agreed (docs/decisions.md): store nested components at every depth, in document order
    (each parent before its children). metadata.component and metadata.tools are not walked."""
    for i, comp in enumerate(items):
        where = f"{path}[{i}]"
        name = comp["name"]
        version = comp.get("version")
        # Agreed: the contract's Component requires a version, so reject the whole SBOM.
        if not isinstance(version, str) or not version.strip():
            raise _invalid_sbom(f"{where} ({name!r}) is missing required field: version")
        purl = comp.get("purl")
        out.append(ParsedComponent(name, version, purl if isinstance(purl, str) else None))
        _flatten(comp.get("components", []), f"{where}.components", out)
