"""Provider-independent structured-output parsing foundation for CreatorOS."""

from creatoros.parsing.enums import FieldRequirement, ParseStatus
from creatoros.parsing.models import (
    ParsedField,
    StructuredFieldSpec,
    StructuredOutputSpec,
    StructuredTextParseResult,
)
from creatoros.parsing.parser import StructuredTextParser, parse_into_model
from creatoros.parsing.text import normalize_field_label, normalize_model_text

__all__ = [
    "FieldRequirement",
    "ParseStatus",
    "ParsedField",
    "StructuredFieldSpec",
    "StructuredOutputSpec",
    "StructuredTextParseResult",
    "StructuredTextParser",
    "normalize_field_label",
    "normalize_model_text",
    "parse_into_model",
]
