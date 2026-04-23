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


def test_validate_verdicts_marks_unknown_article_ids_unverified():
    verdicts, flagged, _ = validate_verdicts(INVALID_ARTICLE_RAW, {"DUO:0000007"})
    assert len(verdicts) == 1
    assert verdicts[0].status == "unverified"
    assert verdicts[0].evidence is None
    assert flagged == ["FAKE:9999999"]


def test_validate_verdicts_keeps_known_article_ids():
    verdicts, flagged, narrative = validate_verdicts(VALID_RAW, {"DUO:0000007", "4.3"})
    assert len(verdicts) == 2
    assert flagged == []
    assert verdicts[0].article_id == "DUO:0000007"
    assert verdicts[1].article_id == "4.3"
    assert "DUO:0000007" in narrative


def test_extract_cited_articles_flags_unknown_inline_tokens():
    answer = (
        "Disease-specific research use [DUO:0000007] is allowed, but [FAKE:9999] "
        "is not a grounded citation."
    )
    valid_cited, flagged = extract_cited_articles(answer, {"DUO:0000007"})
    assert valid_cited == ["DUO:0000007"]
    assert flagged == ["FAKE:9999"]
