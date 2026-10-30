import json
from pathlib import Path
from typing import Any

import pytest

from app.errors import ApiError
from app.services.sbom_validation import parse_and_validate
from tests.sbom_helpers import make_sbom, raw


def _reason(body: bytes) -> tuple[str, str]:
    with pytest.raises(ApiError) as exc:
        parse_and_validate(body)
    assert exc.value.status == 400
    return exc.value.code, exc.value.message


def test_valid_sbom_returns_components_in_order() -> None:
    comps = parse_and_validate(raw(make_sbom(3)))
    assert [c.name for c in comps] == ["lib-0", "lib-1", "lib-2"]
    assert comps[1].version == "1.0.0"
    assert comps[1].purl == "pkg:npm/lib-1@1.0.0"


def test_pod_fixture_is_accepted() -> None:
    comps = parse_and_validate(Path("fixtures/sbom_25_components.json").read_bytes())
    assert len(comps) == 25


@pytest.mark.parametrize("spec", ["1.4", "1.5", "1.6"])
def test_supported_spec_versions(spec: str) -> None:
    assert len(parse_and_validate(raw(make_sbom(2, spec)))) == 2


def test_no_components_is_valid_and_empty() -> None:
    doc = make_sbom(0)
    del doc["components"]
    assert parse_and_validate(raw(doc)) == []


def test_malformed_json() -> None:
    code, msg = _reason(b'{"bomFormat": ')
    assert code == "INVALID_JSON" and "not valid JSON" in msg


def test_plaintext() -> None:
    code, msg = _reason(b"hello, this is not json")
    assert code == "INVALID_JSON" and "not valid JSON" in msg


def test_non_utf8() -> None:
    code, msg = _reason(b"\xff\xfe\x00")
    assert code == "INVALID_JSON" and "UTF-8" in msg


def test_non_object() -> None:
    assert _reason(b"[1, 2]")[1] == "CycloneDX document must be a JSON object"


def test_missing_bomformat() -> None:
    doc = make_sbom(1)
    del doc["bomFormat"]
    assert _reason(raw(doc)) == ("INVALID_SBOM", "missing required field: bomFormat")


def test_wrong_bomformat() -> None:
    doc = make_sbom(1)
    doc["bomFormat"] = "SPDX"
    assert "bomFormat must be 'CycloneDX'" in _reason(raw(doc))[1]


def test_missing_specversion() -> None:
    doc = make_sbom(1)
    del doc["specVersion"]
    assert _reason(raw(doc))[1] == "missing required field: specVersion"


@pytest.mark.parametrize("spec", ["1.3", "2.0", "abc"])
def test_unsupported_specversion(spec: str) -> None:
    msg = _reason(raw(make_sbom(1, spec)))[1]
    assert f"unsupported specVersion '{spec}'" in msg and "1.4, 1.5, 1.6" in msg


def test_component_missing_name_is_named_by_schema() -> None:
    doc = make_sbom(2)
    del doc["components"][1]["name"]
    assert _reason(raw(doc))[1] == "missing required field: name in components[1]"


def test_component_bad_type_enum() -> None:
    doc = make_sbom(1)
    doc["components"][0]["type"] = "nonsense"
    msg = _reason(raw(doc))[1]
    assert msg.startswith("components[0].type:") and "nonsense" in msg


def test_component_without_version_rejects_whole_sbom() -> None:
    doc = make_sbom(3)
    del doc["components"][2]["version"]
    assert _reason(raw(doc))[1] == "components[2] ('lib-2') is missing required field: version"


def test_wrong_type_for_components() -> None:
    doc = make_sbom(1)
    doc["components"] = "nope"
    assert _reason(raw(doc))[1].startswith("components:")


def _nested_sbom() -> dict[str, Any]:
    doc = make_sbom(2)
    child = {"type": "library", "name": "child", "version": "1.1.0", "purl": "pkg:npm/child@1.1.0"}
    grandchild = {"type": "library", "name": "grandchild", "version": "1.2.0"}
    doc["components"][0]["components"] = [{**child, "components": [grandchild]}]
    doc["metadata"] = {
        "component": {"type": "application", "name": "the-product", "version": "9.9.9"},
        "tools": {"components": [{"type": "application", "name": "syft", "version": "1.0"}]},
    }
    return doc


def test_nested_components_are_flattened_in_document_order() -> None:
    comps = parse_and_validate(raw(_nested_sbom()))
    assert [(c.name, c.version, c.purl) for c in comps] == [
        ("lib-0", "0.0.0", "pkg:npm/lib-0@0.0.0"),
        ("child", "1.1.0", "pkg:npm/child@1.1.0"),
        ("grandchild", "1.2.0", None),
        ("lib-1", "1.0.0", "pkg:npm/lib-1@1.0.0"),
    ]


def test_nested_component_without_version_names_its_path() -> None:
    doc = _nested_sbom()
    del doc["components"][0]["components"][0]["components"][0]["version"]
    assert _reason(raw(doc))[1] == (
        "components[0].components[0].components[0] ('grandchild') is missing required field:"
        " version"
    )


def test_duplicate_component_message_is_short() -> None:
    doc = json.loads(Path("fixtures/sbom_25_components.json").read_bytes())
    doc["components"].append(doc["components"][3])
    code, message = _reason(raw(doc))
    assert code == "INVALID_SBOM"
    assert message == "components contains duplicate entries: components[25] repeats components[3]"


def test_nested_duplicate_names_its_path() -> None:
    doc = make_sbom(1)
    child = {"type": "library", "name": "c", "version": "1"}
    doc["components"][0]["components"] = [child, {"type": "library", "name": "d", "version": "1"}]
    doc["components"][0]["components"].append(child)
    assert _reason(raw(doc))[1] == (
        "components[0].components contains duplicate entries:"
        " components[0].components[2] repeats components[0].components[0]"
    )
