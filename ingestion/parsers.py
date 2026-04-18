from pathlib import Path

import fitz
from langchain_core.documents import Document
from rdflib import Graph, Literal as RDFLiteral, Namespace, RDF, RDFS, URIRef

from ingestion.manifest import SourceConfig

OWL = Namespace("http://www.w3.org/2002/07/owl#")
OBO = Namespace("http://purl.obolibrary.org/obo/")
OBO_IN_OWL = Namespace("http://www.geneontology.org/formats/oboInOwl#")


def parse_pdf(pdf_path: Path, source: SourceConfig) -> list[Document]:
    documents: list[Document] = []
    pdf = fitz.open(str(pdf_path))
    try:
        for page_number, page in enumerate(pdf, start=1):
            text = page.get_text("text").strip()
            if not text:
                continue
            documents.append(
                Document(
                    page_content=text,
                    metadata={"page": page_number, "section_title": ""},
                )
            )
    finally:
        pdf.close()
    return documents


def _literal_text(value: object) -> str | None:
    if isinstance(value, RDFLiteral):
        text = str(value).strip()
        return text or None
    return None


def _duo_short_form(node: object) -> str | None:
    if not isinstance(node, URIRef):
        return None

    value = str(node)
    tail = value.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    if tail.startswith("DUO_"):
        return tail.replace("_", ":", 1)
    if tail.startswith("DUO:"):
        return tail
    return None


def _objects_as_text(graph: Graph, subject: URIRef, predicate: URIRef) -> list[str]:
    values: list[str] = []
    for obj in graph.objects(subject, predicate):
        text = _literal_text(obj)
        if text:
            values.append(text)
    return values


def _parents(graph: Graph, subject: URIRef) -> list[str]:
    parents: list[str] = []
    for obj in graph.objects(subject, RDFS.subClassOf):
        short_form = _duo_short_form(obj)
        if short_form:
            parents.append(short_form)
    return sorted(set(parents))


def parse_duo_owl(owl_path: Path, source: SourceConfig) -> list[Document]:
    graph = Graph()
    graph.parse(owl_path)

    documents: list[Document] = []
    for term in sorted(graph.subjects(RDF.type, OWL.Class), key=lambda node: str(node)):
        article_id = _duo_short_form(term)
        if not article_id:
            continue

        labels = _objects_as_text(graph, term, RDFS.label)
        label = labels[0] if labels else article_id
        definitions = _objects_as_text(graph, term, OBO["IAO_0000115"])
        comments = _objects_as_text(graph, term, RDFS.comment)
        body = definitions[0] if definitions else (comments[0] if comments else "")
        synonyms = sorted(set(_objects_as_text(graph, term, OBO_IN_OWL.hasExactSynonym)))
        parents = _parents(graph, term)

        lines = [f"{label} ({article_id})"]
        if body:
            lines.append(body)
        if synonyms:
            lines.append(f"Synonyms: {', '.join(synonyms)}")
        if parents:
            lines.append(f"Parents: {', '.join(parents)}")

        documents.append(
            Document(
                page_content="\n".join(lines),
                metadata={
                    "article_id": article_id,
                    "section_title": label,
                    "page": None,
                },
            )
        )

    return documents
