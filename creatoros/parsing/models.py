"""Typed models for provider-independent structured-output parsing."""

from __future__ import annotations

from pydantic import Field, field_validator, model_validator

from creatoros.core import CreatorOSValidationError
from creatoros.domain import CreatorOSModel
from creatoros.parsing.enums import FieldRequirement, ParseStatus
from creatoros.parsing.text import normalize_field_label


def _trim_required_text(value: str, *, field_name: str) -> str:
    """Trim and reject blank required textual values."""

    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank")
    return normalized_value


def _normalize_optional_value(value: str | None) -> str | None:
    """Trim optional field values while preserving internal formatting."""

    if value is None:
        return None
    return value.strip()


class ParsedField(CreatorOSModel):
    """Represents one parsed structured-output field."""

    name: str
    value: str | None = None
    requirement: FieldRequirement = FieldRequirement.REQUIRED
    present: bool = False
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Normalize field names into canonical label form."""

        return normalize_field_label(value)

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: str | None) -> str | None:
        """Trim surrounding whitespace from parsed values."""

        return _normalize_optional_value(value)

    @model_validator(mode="after")
    def validate_state(self) -> ParsedField:
        """Ensure presence flags and values remain consistent."""

        if self.present and self.value is None:
            raise ValueError("present fields must provide a value")
        return self


class StructuredTextParseResult(CreatorOSModel):
    """Validated result of parsing structured provider text."""

    status: ParseStatus
    fields: dict[str, ParsedField]
    missing_required_fields: tuple[str, ...] = ()
    unknown_fields: tuple[str, ...] = ()
    raw_length: int
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("fields")
    @classmethod
    def validate_fields(cls, value: dict[str, ParsedField]) -> dict[str, ParsedField]:
        """Require canonical field keys that match the contained field names."""

        normalized_fields: dict[str, ParsedField] = {}
        for key, parsed_field in value.items():
            normalized_key = normalize_field_label(key)
            if normalized_key != parsed_field.name:
                raise ValueError("field keys must match canonical parsed field names")
            normalized_fields[normalized_key] = parsed_field
        return normalized_fields

    @field_validator("missing_required_fields", "unknown_fields")
    @classmethod
    def validate_name_tuples(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Normalize and deduplicate field-name tuples."""

        normalized_names = tuple(dict.fromkeys(normalize_field_label(item) for item in value))
        return normalized_names

    @field_validator("raw_length")
    @classmethod
    def validate_raw_length(cls, value: int) -> int:
        """Require non-negative normalized text length."""

        if value < 0:
            raise ValueError("raw_length must be greater than or equal to 0")
        return value

    @property
    def is_success(self) -> bool:
        """Return whether parsing succeeded without omissions."""

        return self.status is ParseStatus.SUCCESS

    @property
    def has_missing_required_fields(self) -> bool:
        """Return whether any required fields are still missing."""

        return bool(self.missing_required_fields)

    def get_value(
        self,
        name: str,
        *,
        required: bool = True,
    ) -> str | None:
        """Return a parsed field value or raise a safe validation error."""

        normalized_name = normalize_field_label(name)
        parsed_field = self.fields.get(normalized_name)
        if parsed_field is None or not parsed_field.present:
            if required:
                raise CreatorOSValidationError(
                    "required parsed field is missing",
                    code="parsed_field_missing",
                    details={"field_name": normalized_name},
                )
            return None
        return parsed_field.value


class StructuredFieldSpec(CreatorOSModel):
    """Declarative definition of one expected structured-output field."""

    name: str
    requirement: FieldRequirement = FieldRequirement.REQUIRED
    allow_blank: bool = False
    multiline: bool = True
    aliases: tuple[str, ...] = ()

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Normalize the canonical field name."""

        return normalize_field_label(value)

    @field_validator("aliases")
    @classmethod
    def validate_aliases(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Normalize aliases and reject duplicates."""

        normalized_aliases = tuple(normalize_field_label(alias) for alias in tuple(value))
        if len(normalized_aliases) != len(set(normalized_aliases)):
            raise ValueError("aliases must be unique")
        return normalized_aliases

    @model_validator(mode="after")
    def validate_alias_relationships(self) -> StructuredFieldSpec:
        """Reject alias relationships that duplicate the canonical field name."""

        if self.name in self.aliases:
            raise ValueError("canonical field name must not also appear as an alias")
        return self


class StructuredOutputSpec(CreatorOSModel):
    """Defines the expected label/value structure for a provider text response."""

    name: str
    fields: tuple[StructuredFieldSpec, ...]
    allow_unknown_fields: bool = False
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Trim and reject blank specification names."""

        return _trim_required_text(value, field_name="name")

    @model_validator(mode="after")
    def validate_fields(self) -> StructuredOutputSpec:
        """Require at least one field and prevent name or alias collisions."""

        if not self.fields:
            raise ValueError("fields must contain at least one specification")

        canonical_names: set[str] = set()
        all_labels: set[str] = set()
        for field_spec in self.fields:
            if field_spec.name in canonical_names:
                raise ValueError("canonical field names must be unique")
            canonical_names.add(field_spec.name)

            candidate_labels = (field_spec.name, *field_spec.aliases)
            for label in candidate_labels:
                if label in all_labels:
                    raise ValueError("field names and aliases must not collide")
                all_labels.add(label)

        return self

    def resolve_field_name(self, label: str) -> str | None:
        """Resolve a canonical field name from a header label or alias."""

        normalized_label = normalize_field_label(label)
        for field_spec in self.fields:
            if normalized_label == field_spec.name or normalized_label in field_spec.aliases:
                return field_spec.name
        return None

    @property
    def required_field_names(self) -> frozenset[str]:
        """Return the immutable set of required canonical field names."""

        return frozenset(
            field_spec.name
            for field_spec in self.fields
            if field_spec.requirement is FieldRequirement.REQUIRED
        )
