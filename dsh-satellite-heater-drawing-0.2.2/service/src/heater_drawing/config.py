"""Configuration limited to B01 resource discovery."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ResourceConfig(BaseModel):
    """Validated paths for separately deployed, read-only resources."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    root: Path
    schema_dir: Path
    template_dir: Path | None = None

    @model_validator(mode="after")
    def validate_paths(self) -> "ResourceConfig":
        root = self.root.resolve()
        schema_dir = self.schema_dir.resolve()
        if not schema_dir.is_relative_to(root):
            raise ValueError("schema_dir must be inside resource root")
        if not schema_dir.is_dir():
            raise ValueError("schema_dir does not exist")
        if self.template_dir is not None:
            template_dir = self.template_dir.resolve()
            if not template_dir.is_relative_to(root):
                raise ValueError("template_dir must be inside resource root")
            if not template_dir.is_dir():
                raise ValueError("template_dir does not exist")
        return self

    @classmethod
    def from_root(cls, root: Path, *, require_template: bool = False) -> "ResourceConfig":
        resolved = root.resolve()
        template = resolved / "templates"
        return cls(
            root=resolved,
            schema_dir=resolved / "schemas",
            template_dir=template if require_template else None,
        )

    @classmethod
    def from_environment(cls, *, require_template: bool = False) -> "ResourceConfig":
        value = os.environ.get("HEATER_DRAWING_RESOURCE_ROOT")
        if not value:
            raise ValueError("HEATER_DRAWING_RESOURCE_ROOT is required")
        return cls.from_root(Path(value), require_template=require_template)


class ServiceConfig(BaseModel):
    """Non-secret service configuration defined by the B01 contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = Field(default=1, frozen=True)
    resource: ResourceConfig

    @field_validator("schema_version", mode="before")
    @classmethod
    def schema_version_is_strict_one(cls, value: Any) -> int:
        if type(value) is not int or value != 1:
            raise ValueError("schema_version must be integer 1")
        return value
