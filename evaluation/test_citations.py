# evaluation/test_citations.py
"""
Unit tests for the citation validator.
Tests: valid anchors pass, invalid anchors are flagged, malformed JSON degrades gracefully.
"""
import pytest
from generation.validator import validate_verdicts, VerdictItem


# ── Fixtures ──────────────────────────────────────────────────────────────────

VALID_RAW = """\
## JSON_VERDICTS
```json
[
  {
    "anchor_id": "DUO:0000007",
    "anchor_type": "duo_term",
    "section_title": "Disease Specific Research",
    "obligation": "Data restricted to disease-specific research.",
    "status": "covered",
    "evidence": "We will use data only for cardiovascular disease research.",
    "rationale": "Researcher explicitly restricts use to disease research.",
    "page": 2,
    "title": "DUO Guidance"
  },
  {
    "anchor_id": "4.3",
    "anchor_type": "numbered_section",
    "section_title": "Data Use Agreements",
    "obligation": "Users must execute a Data Use Agreement.",
    "status": "covered",
    "evidence": "We agree to comply with the applicable Data Use Agreement.",
    "rationale": "DUA compliance explicitly stated.",
    "page": 4,
    "title": "GA4GH Framework"
  }
]
```

## NARRATIVE_SUMMARY
The document satisfies the DUO:0000007 disease-restriction requirement and acknowledges
the Data Use Agreement obligation. No major gaps were identified in the retrieved evidence.
"""

INVALID_ANCHOR_RAW = """\
## JSON_VERDICTS
```json
[
  {
    "anchor_id": "FAKE:9999999",
    "anchor_type": "duo_term",
    "section_title": "Nonexistent Section",
    "obligation": "Made-up obligation",
    "status": "covered",
    "evidence": "Some researcher text.",
    "rationale": "Fabricated citation.",
    "page": 1,
    "title": "Fake Doc"
  }
]
```

## NARRATIVE_SUMMARY
Nothing real here.
"""

MIXED_RAW = """\
## JSON_VERDICTS
```json
[
  {
    "anchor_id": "DUO:0000007",
    "anchor_type": "duo_term",
    "section_title": "Disease Specific Research",
    "obligation": "Data restricted to disease research.",
    "status": "covered",
    "evidence": "Data used for CVD only.",
    "rationale": "Explicit restriction in document.",
    "page": 2,
    "title": "DUO Guidance"
  },
  {
    "anchor_id": "HALLUCINATED:0001",
    "anchor_type": "numbered_section",
    "section_title": "Invented Clause",
    "obligation": "Invented obligation.",
    "status": "covered",
    "evidence": "Some text.",
    "rationale": "Hallucinated citation.",
    "page": 1,
    "title": "Fake"
  }
]
```

## NARRATIVE_SUMMARY
Mixed validity response.
"""

MALFORMED_RAW = "This is not JSON at all. The model just wrote prose."

NO_VERDICTS_SECTION = "The model forgot the section headers entirely."

BARE_JSON_RAW = """\
Some preamble text.

[
  {
    "anchor_id": "1",
    "anchor_type": "numbered_section",
    "section_title": "Purpose",
    "obligation": "Establish data sharing principles.",
    "status": "covered",
    "evidence": "Our project follows GA4GH principles.",
    "rationale": "General alignment stated.",
    "page": 1,
    "title": "Framework"
  }
]

Some postamble text.
"""


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestValidVerdicts:
    def test_valid_anchor_passes(self):
        retrieved = {"DUO:0000007", "4.3", "1"}
        verdicts, flagged, narrative = validate_verdicts(VALID_RAW, retrieved)
        assert len(verdicts) == 2
        assert flagged == []
        assert verdicts[0].anchor_id == "DUO:0000007"
        assert verdicts[0].status == "covered"
        assert verdicts[1].anchor_id == "4.3"

    def test_narrative_extracted(self):
        retrieved = {"DUO:0000007", "4.3"}
        _, _, narrative = validate_verdicts(VALID_RAW, retrieved)
        assert "DUO:0000007" in narrative
        assert len(narrative) > 10


class TestInvalidAnchors:
    def test_invalid_anchor_flagged(self):
        retrieved = {"DUO:0000007", "1"}
        verdicts, flagged, _ = validate_verdicts(INVALID_ANCHOR_RAW, retrieved)
        assert len(verdicts) == 1
        assert verdicts[0].status == "unverified"
        assert verdicts[0].evidence is None
        assert "FAKE:9999999" in flagged

    def test_mixed_anchors_partial_flag(self):
        retrieved = {"DUO:0000007"}
        verdicts, flagged, _ = validate_verdicts(MIXED_RAW, retrieved)
        assert len(verdicts) == 2
        valid_v = next(v for v in verdicts if v.anchor_id == "DUO:0000007")
        invalid_v = next(v for v in verdicts if v.anchor_id == "HALLUCINATED:0001")
        assert valid_v.status == "covered"
        assert invalid_v.status == "unverified"
        assert invalid_v.evidence is None
        assert "HALLUCINATED:0001" in flagged
        assert "DUO:0000007" not in flagged


class TestMalformedOutput:
    def test_pure_prose_returns_empty_verdicts(self):
        verdicts, flagged, _ = validate_verdicts(MALFORMED_RAW, set())
        assert isinstance(verdicts, list)
        assert isinstance(flagged, list)
        # Should not raise; may return empty list or flagged malformed marker
        assert "<malformed JSON output>" in flagged or verdicts == []

    def test_no_section_headers_returns_gracefully(self):
        verdicts, flagged, narrative = validate_verdicts(NO_VERDICTS_SECTION, set())
        assert isinstance(verdicts, list)
        assert isinstance(narrative, str)

    def test_bare_json_fallback(self):
        """Validator should find JSON array even without ## JSON_VERDICTS header."""
        retrieved = {"1"}
        verdicts, flagged, _ = validate_verdicts(BARE_JSON_RAW, retrieved)
        assert len(verdicts) == 1
        assert verdicts[0].anchor_id == "1"
        assert flagged == []

    def test_empty_retrieved_set_flags_all(self):
        """All anchors should be flagged when retrieved set is empty."""
        verdicts, flagged, _ = validate_verdicts(VALID_RAW, set())
        assert all(v.status == "unverified" for v in verdicts)
        assert len(flagged) == len(verdicts)
