# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Validated manifest contract shared by built-in and external plugins."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, field_validator


PLUGIN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
SEMVER_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
API_MAJOR_PATTERN = re.compile(r"^[1-9][0-9]*$")
_ENTRYPOINT_CLASS_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse_semver(value: str) -> tuple[int, int, int]:
    """Return a comparable tuple for an already validated semantic version."""

    if type(value) is not str:
        raise ValueError("version must use exact MAJOR.MINOR.PATCH form")
    match = SEMVER_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError("version must use exact MAJOR.MINOR.PATCH form")
    return tuple(int(part) for part in match.groups())


def split_entrypoint(value: str) -> tuple[PurePosixPath, str]:
    """Validate and split a traversal-safe relative ``file.py:Class`` value."""

    if "\x00" in value or "\\" in value or value.count(":") != 1:
        raise ValueError("entrypoint must use a relative file.py:Class value")
    file_name, class_name = value.split(":", 1)
    path = PurePosixPath(file_name)
    if (
        not file_name
        or path.is_absolute()
        or path.as_posix() != file_name
        or path.suffix != ".py"
        or any(part in {"", ".", ".."} for part in path.parts)
        or _ENTRYPOINT_CLASS_PATTERN.fullmatch(class_name) is None
    ):
        raise ValueError("entrypoint must use a relative file.py:Class value")
    return path, class_name


class PluginManifest(BaseModel):
    """Immutable, strict plugin metadata accepted by the lifecycle manager."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        strict=True,
    )

    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    version: str
    min_app_version: str = Field(alias="minAppVersion")
    description: str = Field(min_length=1, max_length=2000)
    author: str = Field(min_length=1, max_length=200)
    permissions: tuple[str, ...]
    api_version: str = Field(default="1", alias="apiVersion")
    entrypoint: str = "plugin.py:Plugin"

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if PLUGIN_ID_PATTERN.fullmatch(value) is None:
            raise ValueError("plugin id is invalid")
        return value

    @field_validator("version", "min_app_version")
    @classmethod
    def _validate_semver(cls, value: str) -> str:
        parse_semver(value)
        return value

    @field_validator("api_version")
    @classmethod
    def _validate_api_version(cls, value: str) -> str:
        if API_MAJOR_PATTERN.fullmatch(value) is None:
            raise ValueError("apiVersion must be a positive major version")
        return value

    @field_validator("permissions", mode="before")
    @classmethod
    def _require_permission_list(cls, value: object) -> object:
        if not isinstance(value, list):
            raise ValueError("permissions must be a list")
        return tuple(value)

    @field_validator("permissions")
    @classmethod
    def _validate_permissions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(PLUGIN_ID_PATTERN.fullmatch(permission) is None for permission in value):
            raise ValueError("permission ids must use the plugin id syntax")
        if len(set(value)) != len(value):
            raise ValueError("permission ids must be unique")
        return value

    @field_validator("entrypoint")
    @classmethod
    def _validate_entrypoint(cls, value: str) -> str:
        split_entrypoint(value)
        return value
