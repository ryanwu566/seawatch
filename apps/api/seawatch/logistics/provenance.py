"""Provenance rules and aggregation for the logistics module (design §6).

Pure functions only. Enforces the truth boundary:

- a field is ``official`` **only** when its record carries adequate
  :class:`SourceMetadata` that genuinely supports it;
- a ``derived`` field must name its derivation method;
- a :class:`DecisionBrief` always carries a non-empty ``provenance_note``;
- ``summarize`` counts each ``source_type`` so the UI can render an honest
  truth badge. No function can upgrade a ``scenario``/``synthetic`` label.
"""

from __future__ import annotations

from collections.abc import Iterable

from .models import DecisionBrief, SourceMetadata, SourceType


def summarize(records: Iterable[object]) -> dict[str, int]:
    """Count contributing fields by ``source_type``.

    Each record is expected to expose a ``source_type`` attribute. The returned
    mapping always contains all four classes (zero-filled) for a stable shape.
    """

    counts = {level.value: 0 for level in SourceType}
    for record in records:
        source_type = getattr(record, "source_type", None)
        if source_type is None:
            continue
        key = source_type.value if isinstance(source_type, SourceType) else str(source_type)
        if key not in counts:
            raise ValueError(f"unknown source_type: {key!r}")
        counts[key] += 1
    return counts


def carries_note(brief: DecisionBrief) -> bool:
    """True iff the brief carries a non-empty truth-boundary provenance note."""

    note = getattr(brief, "provenance_note", None)
    return isinstance(note, str) and bool(note.strip())


def _has_official_evidence(metadata: SourceMetadata | None) -> bool:
    if metadata is None:
        return False
    return bool(
        metadata.source_name
        and metadata.source_name.strip()
        and metadata.source_reference
        and metadata.source_reference.strip()
    )


def _has_derivation_method(metadata: SourceMetadata | None) -> bool:
    if metadata is None:
        return False
    return bool(metadata.derivation_method and metadata.derivation_method.strip())


def validate_official(record: object) -> None:
    """Reject an ``official``/``derived`` classification lacking real evidence.

    - ``official`` requires ``source_name`` + ``source_reference``.
    - ``derived`` requires ``derivation_method``.
    - ``scenario``/``synthetic`` need no metadata and are never upgraded here.

    Raises :class:`ValueError` when evidence is missing.
    """

    source_type = getattr(record, "source_type", None)
    metadata = getattr(record, "source_metadata", None)
    if source_type is SourceType.OFFICIAL and not _has_official_evidence(metadata):
        raise ValueError(
            "official classification requires SourceMetadata with "
            "source_name and source_reference"
        )
    if source_type is SourceType.DERIVED and not _has_derivation_method(metadata):
        raise ValueError("derived classification requires a named derivation_method")
