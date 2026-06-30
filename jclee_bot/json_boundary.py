from __future__ import annotations

from typing import TypeGuard

type JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
type JsonObject = dict[str, JsonValue]


def json_object(value: object, context: str) -> JsonObject:
    if not is_object_mapping(value):
        raise ValueError(f"{context} did not return a JSON object")
    return {str(key): json_value(item) for key, item in value.items()}


def json_value(value: object) -> JsonValue:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if is_object_list(value):
        return [json_value(item) for item in value]
    if is_object_mapping(value):
        return {str(key): json_value(item) for key, item in value.items()}
    return str(value)


def object_dict(value: object, error: str = "value must be a mapping") -> dict[str, object]:
    if not is_object_mapping(value):
        raise ValueError(error)
    return {str(key): item for key, item in value.items()}


def object_list(value: object, error: str) -> list[object]:
    if not is_object_list(value):
        raise ValueError(error)
    return value


def is_object_mapping(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)
