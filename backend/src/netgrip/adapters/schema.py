"""Response schemas for strict structured output (the OpenAI-compatible adapter sends
`"strict": true`): every object lists all its properties as required and allows nothing else;
an optional field is required but nullable, and consumers treat null as absent."""

from typing import Any

_NULL = {"type": "null"}


def obj(properties: dict[str, dict]) -> dict:
    """A strict object: every property required, no other property allowed."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def string_enum(values: list[str]) -> dict:
    return {"type": "string", "enum": list(values)}


def nullable(schema: dict) -> dict:
    """`schema` or null. Objects and arrays become an anyOf; scalars a type list."""
    t = schema.get("type")
    if t in ("object", "array"):
        return {"anyOf": [schema, _NULL]}
    if isinstance(t, str):
        out = {**schema, "type": [t, "null"]}
        if "enum" in schema:
            out["enum"] = [*schema["enum"], None]
        return out
    raise ValueError(f"cannot make {schema!r} nullable")


def _allows_null(schema: dict) -> bool:
    t = schema.get("type")
    if t == "null" or (isinstance(t, list) and "null" in t):
        return True
    return any(_allows_null(s) for s in schema.get("anyOf", []))


def strict_problems(schema: dict, path: str = "$") -> list[str]:
    """Why `schema` is not valid for strict structured output (empty when it is)."""
    out: list[str] = []
    if path == "$" and schema.get("type") != "object":
        out.append(f"{path}: the root must be an object")
    if "anyOf" in schema:
        for i, s in enumerate(schema["anyOf"]):
            out += strict_problems(s, f"{path}.anyOf[{i}]")
        return out
    t = schema.get("type")
    if t is None:
        return [*out, f"{path}: no type"]
    types = t if isinstance(t, list) else [t]
    if "enum" in schema:
        for v in schema["enum"]:
            if not any(_matches(v, ty) for ty in types):
                out.append(f"{path}: enum value {v!r} does not match type {t!r}")
    if "object" in types:
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is not False:
            out.append(f"{path}: additionalProperties must be false")
        if sorted(schema.get("required", [])) != sorted(props):
            out.append(f"{path}: every property must be required")
        for name, s in props.items():
            out += strict_problems(s, f"{path}.{name}")
    if "array" in types:
        if "items" not in schema:
            out.append(f"{path}: an array needs items")
        else:
            out += strict_problems(schema["items"], f"{path}[]")
    return out


def _matches(value: Any, ty: str) -> bool:
    return {
        "string": isinstance(value, str),
        "null": value is None,
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, int | float) and not isinstance(value, bool),
    }.get(ty, False)


def fill_nulls(value: Any, schema: dict) -> Any:
    """`value` with every omitted nullable property set to null, as a strict provider always
    answers (the fake uses it so scripted answers may leave optional fields out)."""
    if isinstance(value, dict):
        branch = next((s for s in [schema, *schema.get("anyOf", [])] if "properties" in s), None)
        if branch is None:
            return value
        out = dict(value)
        for name, s in branch["properties"].items():
            if name in out:
                out[name] = fill_nulls(out[name], s)
            elif _allows_null(s):
                out[name] = None
        return out
    if isinstance(value, list):
        branch = next((s for s in [schema, *schema.get("anyOf", [])] if "items" in s), None)
        return [fill_nulls(v, branch["items"]) for v in value] if branch else value
    return value
