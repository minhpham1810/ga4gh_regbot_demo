# Demo Example

This example shows the intended MVP demo flow for a mentor review.

## Sample uploaded text

File: `data/samples/sample_dul.txt`

```text
This project studies inherited cardiac disease. Access to the dataset will be limited to approved researchers working on disease-specific research questions.

Researchers must obtain ethics approval from their home institution before accessing controlled data. Access requests will be reviewed by a data access committee.

Approved users must sign a data use agreement and must not attempt to re-identify participants.

The current draft does not explain whether participants may withdraw, whether secondary sharing outside the approved study is allowed, or how long data may be retained after the approved project period.
```

## Example retrieval hits

Illustrative grounded hits for that text:

- `DUO:0000007`
  Disease Specific Research Use
- `DUO:0000021`
  Ethics approval required
- `4.3`
  Framework language requiring a data use agreement
- consent-toolkit clauses covering withdrawal and secondary use language

## Example verdict output

```json
[
  {
    "article_id": "DUO:0000007",
    "article_scheme": "duo",
    "section_title": "Disease Specific Research Use",
    "obligation": "Use of the dataset should be limited to disease-specific research.",
    "status": "covered",
    "evidence": "The draft restricts use to inherited cardiac disease research.",
    "rationale": "The uploaded text narrows use to a specific disease area.",
    "page": null,
    "source_title": "Data Use Ontology"
  },
  {
    "article_id": "DUO:0000021",
    "article_scheme": "duo",
    "section_title": "Ethics approval required",
    "obligation": "Approved users must have ethics approval before access.",
    "status": "covered",
    "evidence": "Researchers must obtain ethics approval from their home institution.",
    "rationale": "The document states an explicit ethics-review prerequisite.",
    "page": null,
    "source_title": "Data Use Ontology"
  },
  {
    "article_id": "consent-withdrawal",
    "article_scheme": "consent_clause",
    "section_title": "Withdrawal",
    "obligation": "Participants should be told whether and how they may withdraw.",
    "status": "missing",
    "evidence": null,
    "rationale": "The sample text does not mention withdrawal rights.",
    "page": 3,
    "source_title": "Consent Clauses for Genomic Research"
  }
]
```

## Example narrative summary

The sample language already covers disease-specific use, ethics approval, data access review, and a signed data use agreement. The main remaining gaps are participant-facing consent details, especially withdrawal, downstream sharing boundaries, and retention/renewal language. Any cited article IDs in the final output should come from the retrieved set; unsupported IDs are downgraded to `unverified` by the validator.
