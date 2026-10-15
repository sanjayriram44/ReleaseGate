"""Compare the app's generated OpenAPI with the shared contract in docs/openapi.yaml.

Phase 3 operations must match; later-phase operations are listed explicitly so the test also
fails when one appears (or is forgotten) without updating the list.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

METHODS = ("get", "put", "post", "patch", "delete")

# Contract operations deliberately not built yet (Phases 4 and 5).
NOT_YET_IMPLEMENTED = {
    ("/api/v1/vulnerabilities/{cveId}/affected-releases", "get"),
    ("/api/v1/incidents", "post"),
    ("/api/v1/incidents/{incidentId}", "get"),
    ("/api/v1/incidents/{incidentId}", "patch"),
    ("/api/v1/incidents/{incidentId}/submissions", "post"),
    ("/api/v1/incidents/{incidentId}/report-data/{stage}", "put"),
    ("/api/v1/incidents/{incidentId}/reports/{stage}", "get"),
    ("/api/v1/test/vulnerability-source", "put"),
}
# Our own endpoints that are not part of the shared contract.
EXTRA_ENDPOINTS = {("/health", "get")}


def _resolve(doc: dict[str, Any], node: Any) -> Any:
    while isinstance(node, dict) and "$ref" in node:
        target: Any = doc
        for part in node["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        node = target
    return node


def _operations(doc: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    ops: dict[tuple[str, str], dict[str, Any]] = {}
    for path, item in doc["paths"].items():
        shared = item.get("parameters", [])
        for method in METHODS:
            if method in item:
                op = dict(item[method])
                op["parameters"] = shared + op.get("parameters", [])
                ops[(path, method)] = op
    return ops


def _json_schema(doc: dict[str, Any], content: dict[str, Any] | None) -> dict[str, Any] | None:
    if not content or "application/json" not in content:
        return None
    return _resolve(doc, content["application/json"].get("schema", {}))  # type: ignore[no-any-return]


def _compare_schema(
    c_doc: dict[str, Any], c: dict[str, Any], g_doc: dict[str, Any], g: dict[str, Any], where: str
) -> list[str]:
    c, g = _resolve(c_doc, c), _resolve(g_doc, g)
    problems: list[str] = []
    if set(c.get("required", [])) != set(g.get("required", [])):
        problems.append(f"{where}: required {c.get('required')} != {g.get('required')}")
    if "enum" in c and c["enum"] != g.get("enum"):
        problems.append(f"{where}: enum {c['enum']} != {g.get('enum')}")
    if c.get("format") and c.get("type") == "string" and g.get("format") != c["format"]:
        problems.append(f"{where}: format {c['format']} != {g.get('format')}")
    for name, sub in c.get("properties", {}).items():
        gprops = g.get("properties", {})
        if name not in gprops:
            problems.append(f"{where}.{name}: missing from generated spec")
            continue
        problems += _compare_schema(c_doc, sub, g_doc, gprops[name], f"{where}.{name}")
    if "items" in c and "items" in g:
        problems += _compare_schema(c_doc, c["items"], g_doc, g["items"], f"{where}[]")
    return problems


@pytest.fixture(scope="module")
def docs(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict[str, Any], dict[str, Any]]:
    from app.config import Settings
    from app.main import create_app

    contract = yaml.safe_load(Path("docs/openapi.yaml").read_text())
    app = create_app(
        Settings(
            db_path=str(tmp_path_factory.mktemp("contract") / "c.db"),
            enable_test_endpoints=True,
        )
    )
    with TestClient(app) as c:
        generated = c.get("/openapi.json").json()
    return contract, generated


def test_operation_sets_match(docs: tuple[dict[str, Any], dict[str, Any]]) -> None:
    contract, generated = docs
    c_ops, g_ops = set(_operations(contract)), set(_operations(generated))
    assert NOT_YET_IMPLEMENTED <= c_ops, "allowlist names operations not in the contract"
    assert c_ops - NOT_YET_IMPLEMENTED - g_ops == set(), "contract operations we don't serve"
    assert g_ops & NOT_YET_IMPLEMENTED == set(), "built operation still on NOT_YET_IMPLEMENTED"
    assert g_ops - c_ops - EXTRA_ENDPOINTS == set(), "operations that are not in the contract"


def test_implemented_operations_match_contract(docs: tuple[dict[str, Any], dict[str, Any]]) -> None:
    contract, generated = docs
    c_ops, g_ops = _operations(contract), _operations(generated)
    problems: list[str] = []
    for key in sorted(set(c_ops) & set(g_ops)):
        c, g = c_ops[key], g_ops[key]
        tag = f"{key[1].upper()} {key[0]}"

        missing = set(c["responses"]) - set(g["responses"])
        if missing:
            problems.append(f"{tag}: response codes missing {sorted(missing)}")

        c_params = {
            (_resolve(contract, p)["name"].lower(), _resolve(contract, p)["in"]): _resolve(
                contract, p
            )
            for p in c["parameters"]
        }
        g_params = {
            (_resolve(generated, p)["name"].lower(), _resolve(generated, p)["in"]): _resolve(
                generated, p
            )
            for p in g["parameters"]
        }
        for pkey, cp in c_params.items():
            if pkey not in g_params:
                problems.append(f"{tag}: parameter {pkey} missing")
            elif bool(cp.get("required")) != bool(g_params[pkey].get("required")):
                problems.append(f"{tag}: parameter {pkey} required flag differs")

        c_body = c.get("requestBody")
        if c_body:
            g_body = g.get("requestBody")
            if not g_body:
                problems.append(f"{tag}: request body missing")
            else:
                cs = _json_schema(contract, _resolve(contract, c_body).get("content"))
                gs = _json_schema(generated, _resolve(generated, g_body).get("content"))
                if cs is not None and gs is not None:
                    problems += _compare_schema(contract, cs, generated, gs, f"{tag} body")

        for code, c_resp in c["responses"].items():
            cs = _json_schema(contract, _resolve(contract, c_resp).get("content"))
            g_resp = g["responses"].get(code)
            if cs is None or g_resp is None:
                continue
            gs = _json_schema(generated, _resolve(generated, g_resp).get("content"))
            if gs is None:
                problems.append(f"{tag} {code}: response body schema missing")
            else:
                problems += _compare_schema(contract, cs, generated, gs, f"{tag} {code}")
    assert problems == []
