"""
Compute Tasks - CPU-Intensive Operations

Tasks in this module are designed for CPU-bound operations.
In Phase 2, these will run on Celery workers with compute_queue.

Worker Configuration (Phase 2):
    celery -A src.tasks worker -Q compute_queue -c 4 --prefetch-multiplier=1

Tasks:
- rerank_documents: Cross-encoder reranking
- extract_entities: Entity extraction from text
"""

import logging
from typing import List, Dict, Any
from src.tasks import task

logger = logging.getLogger(__name__)


@task(name="compute.rerank_documents", queue="compute_queue")
def rerank_documents(query: str, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Rerank documents using cross-encoder model.

    This is a CPU-intensive task that should run on dedicated compute workers.

    Phase 1: Stub (returns documents as-is)
    Phase 2: Actual implementation with BAAI/bge-reranker-v2-m3

    Args:
        query: Search query
        documents: List of documents to rerank

    Returns:
        Reranked documents (sorted by relevance score)
    """
    logger.info(f"[STUB] Reranking {len(documents)} documents for query: {query[:50]}...")

    # Phase 1: Stub - return documents as-is
    logger.warning("Reranking is stubbed in Phase 1, returning documents unchanged")
    return documents

    # Phase 2: Actual implementation
    # from sentence_transformers import CrossEncoder
    #
    # model = CrossEncoder('BAAI/bge-reranker-v2-m3')
    # pairs = [(query, doc['content']) for doc in documents]
    # scores = model.predict(pairs)
    #
    # # Sort by score (descending)
    # ranked = sorted(zip(documents, scores), key=lambda x: x[1], reverse=True)
    # return [doc for doc, score in ranked]


@task(name="compute.extract_entities", queue="compute_queue")
def extract_entities_batch(texts: List[str], entity_types: List[str]) -> List[Dict[str, Any]]:
    """
    Batch entity extraction from multiple texts.

    This is a CPU-intensive task (NER model inference).

    Phase 1: Stub (returns empty results)
    Phase 2: Actual implementation with NER model

    Args:
        texts: List of text strings
        entity_types: Entity types to extract (e.g., ["Person", "Location"])

    Returns:
        List of extraction results
    """
    logger.info(f"[STUB] Extracting entities from {len(texts)} texts...")

    # Phase 1: Stub - return empty results
    logger.warning("Entity extraction is stubbed in Phase 1")
    return [{"entities": [], "text_index": i} for i in range(len(texts))]

    # Phase 2: Actual implementation
    # from transformers import pipeline
    #
    # ner = pipeline("ner", model="your-ner-model")
    # results = []
    #
    # for i, text in enumerate(texts):
    #     entities = ner(text)
    #     # Filter by entity types
    #     filtered = [e for e in entities if e['entity_type'] in entity_types]
    #     results.append({"entities": filtered, "text_index": i})
    #
    # return results


@task(name="compute.semantic_similarity", queue="compute_queue")
def compute_semantic_similarity(text1: str, text2: str) -> float:
    """
    Compute semantic similarity between two texts.

    Phase 1: Stub (returns 0.5)
    Phase 2: Actual implementation with sentence transformers

    Args:
        text1: First text
        text2: Second text

    Returns:
        Similarity score (0.0 to 1.0)
    """
    logger.info(f"[STUB] Computing similarity...")

    # Phase 1: Stub
    return 0.5

    # Phase 2: Actual implementation
    # from sentence_transformers import SentenceTransformer, util
    #
    # model = SentenceTransformer('BAAI/bge-small-zh-v1.5')
    # emb1 = model.encode(text1)
    # emb2 = model.encode(text2)
    # similarity = util.cos_sim(emb1, emb2).item()
    #
    # return similarity
