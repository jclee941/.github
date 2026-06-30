from __future__ import annotations

from typing import cast

type JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
type JsonObject = dict[str, JsonValue]


def json_object(value: object, context: str) -> JsonObject:
    if not isinstance(value, dict):
        raise ValueError(f"{context} did not return a JSON object")
    return {key: json_value(item) for key, item in object_dict(cast(object, value)).items()}


def json_value(value: object) -> JsonValue:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, list):
        return [json_value(item) for item in cast(list[object], value)]
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in object_dict(cast(object, value)).items()}
    return str(value)


def object_dict(value: object, error: str = "value must be a mapping") -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(error)
    raw = cast(dict[object, object], value)
    return {str(key): item for key, item in raw.items()}


def object_list(value: object, error: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(error)
    return cast(list[object], value)
