from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

LOOP_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = LOOP_ROOT.parent


def load_json(relative: str) -> Any:
    path = LOOP_ROOT / relative
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(payload: Any) -> str:
    """按控制面的排版约定序列化：`indent=2` 缩进，末尾换行。

    **生成器必须与它所写文件的排版一致**——`--check` 是解析后语义比对，看不见排版差异，所以
    一旦两者不一致，任何一次 `--write` 都会把整个文件重排：两行语义改动淹没在几十行 diff 里，
    而校验器全程不报警。`test_generator_written_json_round_trips_byte_for_byte` 机器守住这一点。

    此前这里写的是「顶层键每行一条 + 值紧凑」，理由是"`state/*.json` 全部手写成这个形状"。
    那个前提已不成立：`atomic_write_json` 实际只写 `state/backlog.json` 与 `state/current.json`，
    而 `current.json` 连同全部大型人审文件（`work-items.json`、`quality-gates.json`、
    `capability-surface.json`、`tokens.json`…）都是缩进格式；紧凑形状只剩 schemas/templates 这类
    静态小文件在用，而它们根本不经本函数。改缩进后 `current.json` 不再被压平，且嵌套结构（数组、
    子对象）的 diff 回到逐行粒度——紧凑形状会把整个数组塞进一行，任何一次追加都重写那一整行。
    """

    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    # newline="\n" 是**必须**的，不是风格问题：control_plane_digest() 按字节哈希，而
    # .gitattributes 声明 `loop/** text eol=lf`。文本模式默认会在 Windows 把 \n 写成 \r\n，
    # 于是本地算出的 digest 与干净检出（CI）上算出的不同，G-LOOP 会凭空变红。
    temp.write_text(dump_json(payload), encoding="utf-8", newline="\n")
    temp.replace(path)


def parse_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{number} must contain a JSON object")
        records.append(value)
    return records


def control_plane_digest() -> str:
    """Hash authoritative control files while excluding self-referential evidence storage."""

    digest = hashlib.sha256()
    for path in sorted(LOOP_ROOT.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(LOOP_ROOT)
        if relative.parts[0] == "evidence":
            continue
        if relative.as_posix() == "state/evidence-index.json":
            continue
        if "__pycache__" in relative.parts or path.suffix == ".pyc":
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _matches_json_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return type(value) is int
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def validate_against_schema(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Validate the JSON-Schema subset used by loop/schemas without a runtime dependency.

    Supported keywords are deliberately small and explicit: type, required, properties,
    additionalProperties, items, enum, const, pattern, minLength, minimum, maximum,
    minItems and uniqueItems. A schema using an unsupported structural keyword must be
    extended here before it can become an enforced project contract.
    """

    errors: list[str] = []
    expected_types = schema.get("type")
    if expected_types is not None:
        if isinstance(expected_types, str):
            expected_types = [expected_types]
        if not isinstance(expected_types, list) or not all(
            isinstance(item, str) for item in expected_types
        ):
            return [f"{path}: schema type must be a string or string array"]
        if not any(_matches_json_type(value, expected) for expected in expected_types):
            return [f"{path}: expected type {expected_types}, got {type(value).__name__}"]

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected constant {schema['const']!r}, got {value!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value {value!r} is not in enum {schema['enum']!r}")

    if isinstance(value, dict):
        required = schema.get("required", [])
        if not isinstance(required, list):
            errors.append(f"{path}: schema required must be an array")
            required = []
        for key in required:
            if key not in value:
                errors.append(f"{path}: missing required property {key!r}")
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            errors.append(f"{path}: schema properties must be an object")
            properties = {}
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}: additional property {key!r} is not allowed")
        for key, child_schema in properties.items():
            if key in value:
                if not isinstance(child_schema, dict):
                    errors.append(f"{path}.{key}: child schema must be an object")
                else:
                    errors.extend(
                        validate_against_schema(value[key], child_schema, f"{path}.{key}")
                    )

    if isinstance(value, list):
        minimum_items = schema.get("minItems")
        if isinstance(minimum_items, int) and len(value) < minimum_items:
            errors.append(f"{path}: expected at least {minimum_items} items, got {len(value)}")
        if schema.get("uniqueItems") is True:
            serialized = [json.dumps(item, ensure_ascii=False, sort_keys=True) for item in value]
            if len(serialized) != len(set(serialized)):
                errors.append(f"{path}: array items must be unique")
        item_schema = schema.get("items")
        if item_schema is not None:
            if not isinstance(item_schema, dict):
                errors.append(f"{path}: schema items must be an object")
            else:
                for index, item in enumerate(value):
                    errors.extend(validate_against_schema(item, item_schema, f"{path}[{index}]"))

    if isinstance(value, str):
        minimum_length = schema.get("minLength")
        if isinstance(minimum_length, int) and len(value) < minimum_length:
            errors.append(f"{path}: string is shorter than {minimum_length}")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            errors.append(f"{path}: value {value!r} does not match {pattern!r}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and value < minimum:
            errors.append(f"{path}: value {value!r} is below minimum {minimum!r}")
        if isinstance(maximum, (int, float)) and value > maximum:
            errors.append(f"{path}: value {value!r} is above maximum {maximum!r}")

    return errors
