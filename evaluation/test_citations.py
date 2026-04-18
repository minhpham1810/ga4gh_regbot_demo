"""
Unit tests for the citation validator.
Tests: valid articles pass, invalid articles are flagged, malformed JSON degrades
gracefully. Also tests extract_cited_articles() for corpus-QA inline validation.
"""
from generation.validator import extract_cited_articles, validate_verdicts

VALID_RAW = """\
## JSON_VERDICTS
```json
[
  {
    "article_id": "DUO:0000007",
    "article_scheme": "duo",
    "section_title": "Disease Specific Research",
    "obligation": "Data restricted to disease-specific research.",
    "status": "covered",
    "evidence": "We will use data only for cardiovascular disease research.",
    "rationale": "Researcher explicitly restricts use to disease research.",
    "page": 2,
    "source_title": "DUO Guidance"
  },
  {
    "article_id": "4.3",
    "article_scheme": "frs",
    "section_title": "Data Use Agreements",
    "obligation": "Users must execute a Data Use Agreement.",
    "status": "covered",
    "evidence": "We agree to comply with the applicable Data Use Agreement.",
    "rationale": "DUA compliance explicitly stated.",
    "page": 4,
    "source_title": "GA4GH Framework"
  }
]
```

## NARRATIVE_SUMMARY
The document satisfies the DUO:0000007 disease-restriction requirement and acknowledges
the Data Use Agreement obligation. No major gaps were identified in the retrieved evidence.
"""

INVALID_ARTICLE_RAW = """\
## JSON_VERDICTS
```json
[
  {
    "article_id": "FAKE:9999999",
    "article_scheme": "duo",
    "section_title": "Nonexistent Section",
    "obligation": "Made-up obligation",
    "status": "covered",
    "evidence": "Some researcher text.",
    "rationale": "Fabricated citation.",
    "page": 1,
    "source_title": "Fake Doc"
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
    "article_id": "DUO:0000007",
    "article_scheme": "duo",
    "section_title": "Disease Specific Research",
    "obligation": "Data restricted to disease research.",
    "status": "covered",
    "evidence": "Data used for CVD only.",
    "rationale": "Explicit restriction in document.",
    "page": 2,
    "source_title": "DUO Guidance"
  },
  {
    "article_id": "HALLUCINATED:0001",
    "article_scheme": "frs",
    "section_title": "Invented Clause",
    "obligation": "Invented obligation.",
    "status": "covered",
    "evidence": "Some text.",
    "rationale": "Hallucinated citation.",
    "page": 1,
    "source_title": "Fake"
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
    "article_id": "1",
    "article_scheme": "frs",
    "section_title": "Purpose",
    "obligation": "Establish data sharing principles.",
    "status": "covered",
    "evidence": "Our project follows GA4GH principles.",
    "rationale": "General alignment stated.",
    "page": 1,
    "source_title": "Framework"
  }
]

Some postamble text.
"""


class TestValidVerdicts:
    def test_valid_article_passes(self):
        retrieved = {"DUO:0000007", "4.3", "1"}
        verdicts, flagged, narrative = validate_verdicts(VALID_RAW, retrieved)
        assert len(verdicts) == 2
        assert flagged == []
        assert verdicts[0].article_id == "DUO:0000007"
        assert verdicts[0].status == "covered"
        assert verdicts[1].article_id == "4.3"
        assert "DUO:0000007" in narrative


class TestInvalidArticles:
    def test_invalid_article_flagged(self):
        retrieved = {"DUO:0000007", "1"}
        verdicts, flagged, _ = validate_verdicts(INVALID_ARTICLE_RAW, retrieved)
        assert len(verdicts) == 1
        assert verdicts[0].status == "unverified"
        assert verdicts[0].evidence is None
        assert "FAKE:9999999" in flagged

    def test_mixed_articles_partial_flag(self):
        retrieved = {"DUO:0000007"}
        verdicts, flagged, _ = validate_verdicts(MIXED_RAW, retrieved)
        assert len(verdicts) == 2
        valid_verdict = next(v for v in verdicts if v.article_id == "DUO:0000007")
        invalid_verdict = next(v for v in verdicts if v.article_id == "HALLUCINATED:0001")
        assert valid_verdict.status == "covered"
        assert invalid_verdict.status == "unverified"
        assert invalid_verdict.evidence is None
        assert "HALLUCINATED:0001" in flagged
        assert "DUO:0000007" not in flagged


class TestMalformedOutput:
    def test_pure_prose_returns_empty_verdicts(self):
        verdicts, flagged, _ = validate_verdicts(MALFORMED_RAW, set())
        assert isinstance(verdicts, list)
        assert isinstance(flagged, list)
        assert "<malformed JSON output>" in flagged or verdicts == []

    def test_no_section_headers_returns_gracefully(self):
        verdicts, flagged, narrative = validate_verdicts(NO_VERDICTS_SECTION, set())
        assert isinstance(verdicts, list)
        assert isinstance(flagged, list)
        assert isinstance(narrative, str)

    def test_bare_json_fallback(self):
        verdicts, flagged, _ = validate_verdicts(BARE_JSON_RAW, {"1"})
        assert len(verdicts) == 1
        assert verdicts[0].article_id == "1"
        assert flagged == []

    def test_empty_retrieved_set_flags_all(self):
        verdicts, flagged, _ = validate_verdicts(VALID_RAW, set())
        assert all(verdict.status == "unverified" for verdict in verdicts)
        assert len(flagged) == len(verdicts)


class TestExtractCitedArticles:
    def test_valid_inline_citations_recognized(self):
        answer = (
            "Disease-specific research use [DUO:0000007] requires that data is "
            "restricted to a specific disease. The data sharing obligations [data-sharing] "
            "further clarify the scope."
        )
        retrieved = {"DUO:0000007", "data-sharing", "4.3"}
        valid_cited, flagged = extract_cited_articles(answer, retrieved)
        assert "DUO:0000007" in valid_cited
        assert "data-sharing" in valid_cited
        assert flagged == []

    def test_unknown_inline_citations_flagged(self):
        answer = (
            "According to the framework [FAKE:9999], researchers must comply. "
            "However, [DUO:0000007] is a valid requirement."
        )
        retrieved = {"DUO:0000007", "data-sharing"}
        valid_cited, flagged = extract_cited_articles(answer, retrieved)
        assert "DUO:0000007" in valid_cited
        assert "FAKE:9999" in flagged
        assert "DUO:0000007" not in flagged
