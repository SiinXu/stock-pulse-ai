from __future__ import annotations

import json
import math
import re
import struct
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from src.model_pack.errors import ModelPackError
from src.model_pack.models import ParsedModelfile


MAX_MODELFILE_BYTES = 1024 * 1024
ALLOWED_INSTRUCTIONS = frozenset({"FROM", "PARAMETER", "TEMPLATE", "SYSTEM"})
INSTRUCTION_NAME_PATTERN = re.compile(r"^[A-Za-z]+$")
PARAMETER_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
REPEATABLE_PARAMETERS = frozenset({"stop"})
MAX_PORTABLE_INTEGER = (2**53) - 1
PARAMETER_TYPES = {
    "num_ctx": "integer",
    "num_batch": "integer",
    "num_gpu": "integer",
    "main_gpu": "integer",
    "use_mmap": "boolean",
    "num_thread": "integer",
    "draft_num_predict": "integer",
    "num_keep": "integer",
    "seed": "integer",
    "num_predict": "integer",
    "top_k": "integer",
    "top_p": "float",
    "min_p": "float",
    "typical_p": "float",
    "repeat_last_n": "integer",
    "temperature": "float",
    "repeat_penalty": "float",
    "presence_penalty": "float",
    "frequency_penalty": "float",
    "stop": "string_list",
}
_INTEGER_VALUE_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)$")
_MODELFILE_TRIM_CHARACTERS = " "
_DISALLOWED_HORIZONTAL_WHITESPACE = "\t\v\f"
_DISALLOWED_LINE_SEPARATORS = "\x85\u2028\u2029"


def _unsafe(message: str) -> ModelPackError:
    """Return one actionable constrained-Modelfile error."""
    return ModelPackError("unsafe_modelfile", message)


def _reject_json_constant(_constant: str) -> None:
    """Reject non-standard JSON constants before transport projection."""
    raise ValueError


def _require_ollama_printable_text(value: str, *, instruction: str) -> str:
    """Require text that Ollama's rune parser preserves byte-for-byte."""
    for character in value:
        if character == "\n" or character == " ":
            continue
        if unicodedata.category(character)[0] not in {"L", "M", "N", "P", "S"}:
            raise _unsafe(
                f"{instruction} contains text Ollama cannot preserve. "
                "Fix the Modelfile and rebuild the pack."
            )
    return value


def _parse_quoted_parameter_text(raw_value: str) -> str:
    """Parse Ollama's delimiter-only quoted parameter text."""
    value = raw_value.strip(_MODELFILE_TRIM_CHARACTERS)
    if not value:
        raise _unsafe("PARAMETER requires a name and value. Fix the Modelfile and rebuild the pack.")
    if len(value) < 2 or not (value.startswith('"') and value.endswith('"')):
        raise _unsafe(
            "PARAMETER stop values must use one complete pair of double quotes. "
            "Fix the Modelfile and rebuild the pack."
        )
    inner = value[1:-1]
    if '"' in inner:
        raise _unsafe(
            "PARAMETER quoted text must not contain inner double quotes. "
            "Fix the Modelfile and rebuild the pack."
        )
    return _require_ollama_printable_text(inner, instruction="PARAMETER stop")


def _parse_parameter_value(name: str, raw_value: str) -> Any:
    """Parse one value using the supported Ollama option's concrete type."""
    value = raw_value.strip(_MODELFILE_TRIM_CHARACTERS)
    if not value:
        raise _unsafe("PARAMETER requires a name and value. Fix the Modelfile and rebuild the pack.")
    parameter_type = PARAMETER_TYPES[name]
    if parameter_type == "string_list":
        return _parse_quoted_parameter_text(value)
    if parameter_type == "boolean":
        if value not in {"true", "false"}:
            raise _unsafe(
                f"PARAMETER {name} requires lowercase true or false. "
                "Fix the Modelfile and rebuild the pack."
            )
        return value == "true"
    if parameter_type == "integer":
        if _INTEGER_VALUE_PATTERN.fullmatch(value) is None:
            raise _unsafe(
                f"PARAMETER {name} requires a base-10 integer. "
                "Fix the Modelfile and rebuild the pack."
            )
        decoded = int(value, 10)
        if abs(decoded) > MAX_PORTABLE_INTEGER:
            raise _unsafe(
                "PARAMETER integers must be within the portable JSON safe range. "
                "Fix the Modelfile and rebuild the pack."
            )
        return decoded
    try:
        decoded = json.loads(
            value,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise _unsafe(
            f"PARAMETER {name} requires a finite JSON number. "
            "Fix the Modelfile and rebuild the pack."
        ) from exc
    if isinstance(decoded, bool) or not isinstance(decoded, (int, float)):
        raise _unsafe(
            f"PARAMETER {name} requires a finite JSON number. "
            "Fix the Modelfile and rebuild the pack."
        )
    try:
        decoded_float = float(decoded)
        decimal_value = Decimal(value)
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise _unsafe(
            f"PARAMETER {name} requires a finite JSON number. "
            "Fix the Modelfile and rebuild the pack."
        ) from exc
    if not math.isfinite(decoded_float) or not decimal_value.is_finite():
        raise _unsafe(
            f"PARAMETER {name} requires a finite JSON number. "
            "Fix the Modelfile and rebuild the pack."
        )
    try:
        portable_float = struct.unpack("!f", struct.pack("!f", decoded_float))[0]
    except (OverflowError, struct.error):
        raise _unsafe(
            f"PARAMETER {name} must fit Ollama's finite 32-bit float range. "
            "Fix the Modelfile and rebuild the pack."
        )
    if not math.isfinite(portable_float):
        raise _unsafe(
            f"PARAMETER {name} must fit Ollama's finite 32-bit float range. "
            "Fix the Modelfile and rebuild the pack."
        )
    if decimal_value != 0 and portable_float == 0.0:
        raise _unsafe(
            f"PARAMETER {name} must not underflow Ollama's 32-bit float range. "
            "Fix the Modelfile and rebuild the pack."
        )
    if portable_float == 0.0:
        return 0
    portable_bits = struct.pack("!f", portable_float)
    for precision in range(1, 10):
        candidate = float(format(portable_float, f".{precision}g"))
        if struct.pack("!f", candidate) == portable_bits:
            return candidate
    raise AssertionError("finite float32 must have a portable decimal projection")


def _parse_text_value(
    lines: List[str],
    index: int,
    initial: str,
    *,
    instruction: str,
) -> Tuple[str, int]:
    """Parse one single-line or triple-quoted text instruction."""
    value = initial.strip(_MODELFILE_TRIM_CHARACTERS)
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
        return _require_ollama_printable_text(
            value,
            instruction=instruction,
        ), index

    remainder = value[3:]
    if '"""' in remainder:
        content, trailing = remainder.split('"""', 1)
        if trailing.strip(_MODELFILE_TRIM_CHARACTERS):
            raise _unsafe(
                f"{instruction} has content after its closing delimiter. "
                "Fix the Modelfile and rebuild the pack."
            )
        return _require_ollama_printable_text(
            content,
            instruction=instruction,
        ), index

    block_lines = [remainder]
    cursor = index + 1
    while cursor < len(lines):
        line = lines[cursor]
        if '"""' in line:
            content, trailing = line.split('"""', 1)
            block_lines.append(content)
            if trailing.strip(_MODELFILE_TRIM_CHARACTERS):
                raise _unsafe(
                    f"{instruction} has content after its closing delimiter. "
                    "Fix the Modelfile and rebuild the pack."
                )
            return _require_ollama_printable_text(
                "\n".join(block_lines),
                instruction=instruction,
            ), cursor
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
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _unsafe("Modelfile must use UTF-8. Rebuild the pack.") from exc
    if "\x00" in text:
        raise _unsafe("Modelfile contains a null byte. Rebuild the pack.")
    if "\ufeff" in text:
        raise _unsafe(
            "Modelfile must not contain a UTF-8 byte-order mark; rebuild the pack."
        )
    if any(separator in text for separator in _DISALLOWED_LINE_SEPARATORS):
        raise _unsafe(
            "Modelfile must use LF or CRLF line endings; rebuild the pack."
        )
    text = text.replace("\r\n", "\n")
    if "\r" in text:
        raise _unsafe(
            "Modelfile must use LF or CRLF line endings; rebuild the pack."
        )
    if any(character in text for character in _DISALLOWED_HORIZONTAL_WHITESPACE):
        raise _unsafe(
            "Modelfile syntax must use ASCII spaces, not tabs or other separators. "
            "Fix the file and rebuild the pack."
        )

    lines = text.split("\n")
    from_file: Optional[str] = None
    parameters: Dict[str, Any] = {}
    template: Optional[str] = None
    system: Optional[str] = None
    index = 0
    while index < len(lines):
        stripped = lines[index].strip(_MODELFILE_TRIM_CHARACTERS)
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        instruction, separator, raw_value = stripped.partition(" ")
        if INSTRUCTION_NAME_PATTERN.fullmatch(instruction) is None:
            raise _unsafe(
                "Modelfile instruction names must use ASCII letters. "
                "Fix the file and rebuild the pack."
            )
        instruction = instruction.upper()
        if instruction not in ALLOWED_INSTRUCTIONS:
            raise _unsafe(
                f"Remove the unsupported instruction {instruction} from Modelfile "
                "and rebuild the pack."
            )
        if not separator or not raw_value.strip(_MODELFILE_TRIM_CHARACTERS):
            raise _unsafe(
                f"{instruction} requires a value. Fix the Modelfile and rebuild the pack."
            )

        if instruction == "FROM":
            if from_file is not None:
                raise _unsafe("Modelfile must contain exactly one FROM instruction.")
            candidate = raw_value.strip(_MODELFILE_TRIM_CHARACTERS)
            if candidate.startswith("./"):
                candidate = candidate[2:]
            if candidate != expected_gguf_file:
                raise _unsafe(
                    f"FROM must reference {expected_gguf_file} from this Model Pack. "
                    "Remove external or arbitrary paths and rebuild the pack."
                )
            from_file = candidate
        elif instruction == "PARAMETER":
            name, value_separator, value = raw_value.strip(
                _MODELFILE_TRIM_CHARACTERS
            ).partition(" ")
            if not value_separator or not PARAMETER_NAME_PATTERN.fullmatch(name):
                raise _unsafe(
                    "PARAMETER requires a safe name and value. "
                    "Fix the Modelfile and rebuild the pack."
                )
            if name not in PARAMETER_TYPES:
                raise _unsafe(
                    f"PARAMETER {name} is not a supported lowercase Ollama option. "
                    "Fix the Modelfile and rebuild the pack."
                )
            parsed_value = _parse_parameter_value(name, value)
            if name in parameters:
                if name not in REPEATABLE_PARAMETERS:
                    raise _unsafe(
                        (
                            f"PARAMETER {name} may appear only once. "
                            "Only stop may be repeated; rebuild the pack."
                        )
                    )
                previous = parameters[name]
                if isinstance(previous, list):
                    previous.append(parsed_value)
                else:
                    parameters[name] = [previous, parsed_value]
            else:
                parameters[name] = (
                    [parsed_value]
                    if name in REPEATABLE_PARAMETERS
                    else parsed_value
                )
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
