from config import MANIFEST_PATH
from ingestion.manifest import load_manifest


def test_manifest_loads():
    sources = load_manifest(MANIFEST_PATH)
    assert len(sources) == 8


def test_duo_is_owl():
    sources = load_manifest(MANIFEST_PATH)
    duo = next(source for source in sources if source.id == "duo")
    assert duo.source_kind == "owl"


def test_six_consent_toolkit_sources():
    sources = load_manifest(MANIFEST_PATH)
    consent_sources = [source for source in sources if source.doc_type == "consent_toolkit"]
    assert len(consent_sources) == 6


def test_required_fields_present():
    sources = load_manifest(MANIFEST_PATH)
    required_fields = (
        "id",
        "title",
        "source_kind",
        "url",
        "doc_type",
        "framework_domain",
        "article_scheme",
    )
    for source in sources:
        data = source.model_dump()
        for field in required_fields:
            assert data[field], f"{field} missing for source {source.id}"


def test_article_scheme_values():
    sources = load_manifest(MANIFEST_PATH)
    allowed = {"frs", "duo", "consent_clause"}
    assert {source.article_scheme for source in sources}.issubset(allowed)
