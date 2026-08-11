# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Validated manifest contract shared by built-in and external plugins."""

from __future__ import annotations

import math
import re
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PLUGIN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
# Descriptive permission IDs (legacy plugin-id style) plus ToolSurface capability
# form ``name:action`` so agent_tool plugins can declare the same strings their
# ToolPolicy.permissions require. Colon is allowed only once as the separator.
PERMISSION_ID_PATTERN = re.compile(
    r"^(?:[a-z0-9][a-z0-9._-]*|[a-z][a-z0-9_]{0,31}:[a-z][a-z0-9_]{0,31})$"
)
SEMVER_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
API_MAJOR_PATTERN = re.compile(r"^[1-9][0-9]*$")
_ENTRYPOINT_CLASS_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PLUGIN_SETTING_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")

# Stable load-time error when an agent_tool requires undeclared capabilities.
MANIFEST_PERMISSIONS_UNDECLARED = "manifest_permissions_undeclared"


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


PluginSettingDataType = Literal["string", "integer", "number", "boolean"]
PluginSettingUIControl = Literal[
    "text",
    "password",
    "number",
    "select",
    "textarea",
    "switch",
]
PluginSettingScalar = str | int | float | bool


class PluginSettingOption(BaseModel):
    """One finite option declared by a plugin setting."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        strict=True,
        allow_inf_nan=False,
    )

    label: str = Field(min_length=1, max_length=200)
    value: PluginSettingScalar

    @field_validator("value")
    @classmethod
    def _reject_non_finite_value(cls, value: PluginSettingScalar) -> PluginSettingScalar:
        if type(value) is float and not math.isfinite(value):
            raise ValueError("setting option values must be finite")
        return value


class PluginSettingValidation(BaseModel):
    """Bounded validation metadata supported by the generated Settings UI."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        strict=True,
        allow_inf_nan=False,
    )

    minimum: int | float | None = None
    maximum: int | float | None = None
    min_length: int | None = Field(default=None, alias="minLength", ge=0, le=100_000)
    max_length: int | None = Field(default=None, alias="maxLength", ge=0, le=100_000)
    pattern: str | None = Field(default=None, max_length=512)

    @field_validator("minimum", "maximum")
    @classmethod
    def _reject_non_finite_bound(cls, value: int | float | None) -> int | float | None:
        if type(value) is float and not math.isfinite(value):
            raise ValueError("numeric bounds must be finite")
        return value

    @field_validator("pattern")
    @classmethod
    def _validate_pattern(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                re.compile(value)
            except re.error as exc:
                raise ValueError("setting pattern must be a valid regular expression") from exc
        return value

    @model_validator(mode="after")
    def _validate_ranges(self) -> "PluginSettingValidation":
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("minimum must not exceed maximum")
        if (
            self.min_length is not None
            and self.max_length is not None
            and self.min_length > self.max_length
        ):
            raise ValueError("minLength must not exceed maxLength")
        return self


class PluginSettingDefinition(BaseModel):
    """Strict declarative field contract supplied in ``manifest.json``."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        strict=True,
        allow_inf_nan=False,
    )

    key: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    data_type: PluginSettingDataType = Field(alias="dataType")
    ui_control: PluginSettingUIControl = Field(alias="uiControl")
    is_sensitive: bool = Field(default=False, alias="isSensitive")
    is_required: bool = Field(default=False, alias="isRequired")
    default_value: PluginSettingScalar | None = Field(default=None, alias="defaultValue")
    options: tuple[PluginSettingOption, ...] = ()
    validation: PluginSettingValidation = Field(default_factory=PluginSettingValidation)
    display_order: int = Field(default=100, alias="displayOrder", ge=0, le=100_000)

    @field_validator("key")
    @classmethod
    def _validate_key(cls, value: str) -> str:
        if PLUGIN_SETTING_KEY_PATTERN.fullmatch(value) is None:
            raise ValueError("setting key must use lowercase plugin-setting syntax")
        return value

    @field_validator("options", mode="before")
    @classmethod
    def _require_option_list(cls, value: object) -> object:
        if not isinstance(value, list):
            raise ValueError("setting options must be a list")
        return tuple(value)

    @model_validator(mode="after")
    def _validate_contract(self) -> "PluginSettingDefinition":
        allowed_controls = {
            "string": {"text", "password", "select", "textarea"},
            "integer": {"number", "select"},
            "number": {"number", "select"},
            "boolean": {"switch", "select"},
        }
        if self.ui_control not in allowed_controls[self.data_type]:
            raise ValueError("setting uiControl is incompatible with dataType")
        if self.is_sensitive and (
            self.data_type != "string" or self.ui_control != "password"
        ):
            raise ValueError("sensitive settings must use string/password")
        if self.is_sensitive and self.default_value is not None:
            raise ValueError("sensitive settings cannot declare plaintext defaults")
        if self.ui_control == "select" and not self.options:
            raise ValueError("select settings must declare at least one option")
        if self.ui_control != "select" and self.options:
            raise ValueError("only select settings may declare options")
        option_identities = {(type(option.value).__name__, repr(option.value)) for option in self.options}
        if len(option_identities) != len(self.options):
            raise ValueError("setting option values must be unique")
        for option in self.options:
            validate_plugin_setting_value(self, option.value, allow_none=False)
        if self.default_value is not None:
            validate_plugin_setting_value(self, self.default_value, allow_none=False)
        if self.data_type == "string" and (
            self.validation.minimum is not None or self.validation.maximum is not None
        ):
            raise ValueError("string settings cannot declare numeric bounds")
        if self.data_type != "string" and (
            self.validation.min_length is not None
            or self.validation.max_length is not None
            or self.validation.pattern is not None
        ):
            raise ValueError("non-string settings cannot declare string validation")
        return self


def validate_plugin_setting_value(
    definition: PluginSettingDefinition,
    value: object,
    *,
    allow_none: bool,
) -> PluginSettingScalar | None:
    """Validate one runtime value without coercion and return it unchanged."""

    if value is None:
        if allow_none:
            return None
        raise ValueError("setting value is required")
    if definition.data_type == "string":
        if type(value) is not str:
            raise ValueError("setting value must be a string")
        if definition.is_required and not value.strip():
            raise ValueError("required setting value must not be blank")
        validation = definition.validation
        if validation.min_length is not None and len(value) < validation.min_length:
            raise ValueError("setting value is shorter than minLength")
        if validation.max_length is not None and len(value) > validation.max_length:
            raise ValueError("setting value is longer than maxLength")
        if validation.pattern is not None and re.search(validation.pattern, value) is None:
            raise ValueError("setting value does not match pattern")
    elif definition.data_type == "boolean":
        if type(value) is not bool:
            raise ValueError("setting value must be a boolean")
    elif definition.data_type == "integer":
        if type(value) is not int:
            raise ValueError("setting value must be an integer")
    else:
        if type(value) not in {int, float}:
            raise ValueError("setting value must be a number")
        if type(value) is float and not math.isfinite(value):
            raise ValueError("setting value must be finite")

    if definition.data_type in {"integer", "number"}:
        numeric = value
        if definition.validation.minimum is not None and numeric < definition.validation.minimum:
            raise ValueError("setting value is below minimum")
        if definition.validation.maximum is not None and numeric > definition.validation.maximum:
            raise ValueError("setting value is above maximum")
    if definition.options and not any(
        type(value) is type(option.value) and value == option.value
        for option in definition.options
    ):
        raise ValueError("setting value is not a declared option")
    return value


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
    settings: tuple[PluginSettingDefinition, ...] = ()

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
        if any(
            type(permission) is not str
            or PERMISSION_ID_PATTERN.fullmatch(permission) is None
            for permission in value
        ):
            raise ValueError(
                "permission ids must use plugin-id syntax or name:action capability form"
            )
        if len(set(value)) != len(value):
            raise ValueError("permission ids must be unique")
        return value

    @field_validator("entrypoint")
    @classmethod
    def _validate_entrypoint(cls, value: str) -> str:
        split_entrypoint(value)
        return value

    @field_validator("settings", mode="before")
    @classmethod
    def _require_settings_list(cls, value: object) -> object:
        if not isinstance(value, list):
            raise ValueError("settings must be a list")
        return tuple(value)

    @model_validator(mode="after")
    def _validate_setting_keys(self) -> "PluginManifest":
        keys = [setting.key for setting in self.settings]
        if len(set(keys)) != len(keys):
            raise ValueError("plugin setting keys must be unique")
        return self
