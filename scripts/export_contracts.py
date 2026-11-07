"""Export the actual API and source schemas for frontend generation and drift checks."""

import json
from pathlib import Path

from retentionops.api import create_app
from retentionops.data import Snapshot
from retentionops.events import Event


def typescript_type(schema):
    """Translate the schema subset emitted by this API; unsupported new constructs fail closed."""
    if set(schema) <= {"title", "description", "default", "examples"}:
        return "unknown"  # JSON Schema without a type constraint, e.g. validation error input.
    if "$ref" in schema:
        prefix = "#/components/schemas/"
        if not schema["$ref"].startswith(prefix):
            raise ValueError("Only local OpenAPI schema references are supported")
        name = schema["$ref"][len(prefix) :]
        return f'components["schemas"][{json.dumps(name)}]'
    if "enum" in schema:
        return " | ".join(json.dumps(v) for v in schema["enum"])
    if "const" in schema:
        return json.dumps(schema["const"])
    if "anyOf" in schema:
        return " | ".join(typescript_type(v) for v in schema["anyOf"])
    kind = schema.get("type")
    if kind in ("string", "integer", "number", "boolean", "null"):
        return {"integer": "number"}.get(kind, kind)
    if kind == "array":
        return f"Array<{typescript_type(schema['items'])}>"
    if kind == "object":
        if "properties" in schema:
            required = set(schema.get("required", []))
            fields = [
                f"{json.dumps(name)}{'' if name in required else '?'}: {typescript_type(value)};"
                for name, value in schema["properties"].items()
            ]
            return "{ " + " ".join(fields) + " }"
        extra = schema.get("additionalProperties", True)
        return f"Record<string, {typescript_type(extra) if isinstance(extra, dict) else 'unknown'}>"
    raise ValueError(f"Unsupported TypeScript contract construct: {schema}")


def frontend_types(openapi):
    schemas = openapi["components"]["schemas"]
    lines = [
        "// Generated from FastAPI OpenAPI by scripts/export_contracts.py; do not edit.",
        "// Schema types only; unsupported schema constructs fail generation.",
        "export interface components { schemas: {",
    ]
    lines.extend(
        f"{json.dumps(name)}: {typescript_type(schema)};" for name, schema in schemas.items()
    )
    return "\n".join([*lines, "}; }", ""])


def main():
    contracts = Path(__file__).resolve().parents[1] / "contracts"
    openapi = create_app().openapi()
    for name, schema in (
        ("openapi.json", openapi),
        ("synthetic_snapshot.schema.json", Snapshot.model_json_schema()),
        ("subscription_event.schema.json", Event.model_json_schema()),
    ):
        (contracts / name).write_text(json.dumps(schema, indent=2) + "\n")
    target = contracts.parent / "apps/web/lib/schema.d.ts"
    target.write_text(frontend_types(openapi))


if __name__ == "__main__":
    main()
