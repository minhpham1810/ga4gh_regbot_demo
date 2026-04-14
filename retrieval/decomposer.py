# retrieval/decomposer.py
"""
TODO: Sub-query decomposition for multi-faceted compliance questions.
For MVP this is a passthrough stub — returns the query unchanged.
"""
from typing import List


def decompose_query(query: str) -> List[str]:
    """
    Decompose a complex query into sub-queries.
    MVP: returns the original query as a single-element list.
    """
    return [query]
