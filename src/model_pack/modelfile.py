from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from src.model_pack.errors import ModelPackError
from src.model_pack.models import ParsedModelfile


MAX_MODELFILE_BYTES = 1024 * 1024
ALLOWED_INSTRUCTIONS = frozenset({"FROM", "PARAMETER", "TEMPLATE", "SYSTEM"})
PARAMETER_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
REPEATABLE_PARAMETERS = frozenset({"stop"})


def _unsafe(message: str) -> ModelPackError:
    """Return one actionable constrained-Modelfile error."""
    return ModelPackError("unsafe_modelfile", message)


def _parse_data_value(raw_value: str) -> Any:
    """Parse one scalar PARAMETER value without accepting containers."""
    value = raw_value.strip()
    if not value:
        raise _unsafe("PARAMETER requires a name and value. Fix the Modelfile and rebuild the pack.")
    try:
        decoded = json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return value
    if decoded is None or isinstance(decoded, (dict, list)):
        return value
    return decoded


def _parse_text_value(
    lines: List[str],
    index: int,
    initial: str,
    *,
    instruction: str,
) -> Tuple[str, int]:
    """Parse one single-line or triple-quoted text instruction."""
    value = initial.strip()
    if not value:
        raise _unsafe(
            f"{instruction} requires text. Fix the Modelfile and rebuild the pack."
        )
    if not value.startswith('"""'):
        if value.startswith(('"', "'", "`")):
            raise _unsafe(
                f"{instruction} single-line text must not use outer quotes. "
                "Use unquoted text or a triple-quoted block and rebuild the pack."
            )
        return value, index

    remainder = value[3:]
    if '"""' in remainder:
        content, trailing = remainder.split('"""', 1)
        if trailing.strip():
            raise _unsafe(
                f"{instruction} has content after its closing delimiter. "
                "Fix the Modelfile and rebuild the pack."
            )
        return content, index

    block_lines = []
    if remainder:
        block_lines.append(remainder)
    cursor = index + 1
    while cursor < len(lines):
        line = lines[cursor]
        if '"""' in line:
            content, trailing = line.split('"""', 1)
            block_lines.append(content)
            if trailing.strip():
                raise _unsafe(
                    f"{instruction} has content after its closing delimiter. "
                    "Fix the Modelfile and rebuild the pack."
                )
            return "\n".join(block_lines), cursor
        block_lines.append(line)
        cursor += 1
    raise _unsafe(
        f"{instruction} has an unterminated triple-quoted block. "
        "Fix the Modelfile and rebuild the pack."
    )


def parse_modelfile(payload: bytes, *, expected_gguf_file: str) -> ParsedModelfile:
    """Parse the data-only Modelfile subset bound to one GGUF filename."""
    if not payload or len(payload) > MAX_MODELFILE_BYTES:
        raise _unsafe(
            f"Modelfile must contain between 1 and {MAX_MODELFILE_BYTES} bytes. "
            "Fix the Modelfile and rebuild the pack."
        )
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _unsafe("Modelfile must use UTF-8. Rebuild the pack.") from exc
    if "\x00" in text:
        raise _unsafe("Modelfile contains a null byte. Rebuild the pack.")

    lines = text.splitlines()
    from_file: Optional[str] = None
    parameters: Dict[str, Any] = {}
    template: Optional[str] = None
    system: Optional[str] = None
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        instruction, separator, raw_value = stripped.partition(" ")
        instruction = instruction.upper()
        if instruction not in ALLOWED_INSTRUCTIONS:
            raise _unsafe(
                f"Remove the unsupported instruction {instruction} from Modelfile "
                "and rebuild the pack."
            )
        if not separator or not raw_value.strip():
            raise _unsafe(
                f"{instruction} requires a value. Fix the Modelfile and rebuild the pack."
            )

        if instruction == "FROM":
            if from_file is not None:
                raise _unsafe("Modelfile must contain exactly one FROM instruction.")
            candidate = raw_value.strip()
            if candidate.startswith("./"):
                candidate = candidate[2:]
            if candidate != expected_gguf_file:
                raise _unsafe(
                    f"FROM must reference {expected_gguf_file} from this Model Pack. "
                    "Remove external or arbitrary paths and rebuild the pack."
                )
            from_file = candidate
        elif instruction == "PARAMETER":
            name, value_separator, value = raw_value.strip().partition(" ")
            normalized_name = name.lower()
            if (
                not value_separator
                or not PARAMETER_NAME_PATTERN.fullmatch(normalized_name)
            ):
                raise _unsafe(
                    "PARAMETER requires a safe name and value. "
                    "Fix the Modelfile and rebuild the pack."
                )
            parsed_value = _parse_data_value(value)
            if normalized_name in parameters:
                if normalized_name not in REPEATABLE_PARAMETERS:
                    raise _unsafe(
                        (
                            f"PARAMETER {normalized_name} may appear only once. "
                            "Only stop may be repeated; rebuild the pack."
                        )
                    )
                previous = parameters[normalized_name]
                if isinstance(previous, list):
                    previous.append(parsed_value)
                else:
                    parameters[normalized_name] = [previous, parsed_value]
            else:
                parameters[normalized_name] = parsed_value
        elif instruction == "TEMPLATE":
            if template is not None:
                raise _unsafe("Modelfile may contain only one TEMPLATE instruction.")
            template, index = _parse_text_value(
                lines,
                index,
                raw_value,
                instruction=instruction,
            )
        elif instruction == "SYSTEM":
            if system is not None:
                raise _unsafe("Modelfile may contain only one SYSTEM instruction.")
            system, index = _parse_text_value(
                lines,
                index,
                raw_value,
                instruction=instruction,
            )
        index += 1

    if from_file is None:
        raise _unsafe(
            f"Modelfile must contain FROM ./{expected_gguf_file}. "
            "Fix the Modelfile and rebuild the pack."
        )
    return ParsedModelfile(
        from_file=from_file,
        parameters=parameters,
        template=template,
        system=system,
    )


__all__ = [
    "ALLOWED_INSTRUCTIONS",
    "MAX_MODELFILE_BYTES",
    "REPEATABLE_PARAMETERS",
    "parse_modelfile",
]
