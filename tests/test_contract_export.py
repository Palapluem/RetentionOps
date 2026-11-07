import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "export_contracts", Path(__file__).parents[1] / "scripts/export_contracts.py"
)
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


def test_nullable_arrays_enums_and_required_fields():
    schema = {
        "type": "object",
        "required": ["id"],
        "properties": {
            "id": {"type": "string"},
            "values": {
                "type": "array",
                "items": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            },
            "mode": {"enum": ["synthetic", "historical"]},
            "counts": {"type": "object", "additionalProperties": {"type": "number"}},
        },
    }
    result = export.typescript_type(schema)
    assert '"id": string' in result
    assert '"values"?: Array<number | null>' in result
    assert '"mode"?: "synthetic" | "historical"' in result
    assert "Record<string, number>" in result


def test_local_reference_and_unsupported_constructs():
    assert export.typescript_type({"title": "Input"}) == "unknown"
    assert (
        export.typescript_type({"$ref": "#/components/schemas/Overview"})
        == 'components["schemas"]["Overview"]'
    )
    with pytest.raises(ValueError):
        export.typescript_type({"$ref": "https://external/schema"})
    with pytest.raises(ValueError):
        export.typescript_type({"oneOf": [{"type": "string"}]})
