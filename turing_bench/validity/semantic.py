"""Layer 3: Semantic similarity - embedding-based comparison."""

from typing import Tuple


def semantic_check(
    candidate_output: str,
    baseline_output: str,
    similarity_threshold: float = 0.92,
    use_embeddings: bool = True,
) -> Tuple[bool, str, float]:
    """
    Layer 3 semantic similarity validation.

    Uses sentence-transformers for embedding-based similarity.
    Handles precision changes correctly (fp32 → bf16).

    Args:
        candidate_output: Generated output to validate
        baseline_output: Reference baseline output
        similarity_threshold: Cosine similarity threshold (0.92 typical)
        use_embeddings: Whether to use embedding-based comparison

    Returns:
        Tuple of (passed, message, similarity_score)
    """

    if not use_embeddings:
        # Fallback to exact match
        is_exact = candidate_output.strip() == baseline_output.strip()
        similarity = 1.0 if is_exact else 0.0
        return is_exact, "Fallback to exact match", similarity

    try:
        from sentence_transformers import SentenceTransformer

        # Load lightweight embedding model (22MB, CPU-only)
        model = SentenceTransformer("all-MiniLM-L6-v2")

        # Encode both outputs
        embeddings = model.encode([baseline_output, candidate_output])
        baseline_emb = embeddings[0]
        candidate_emb = embeddings[1]

        # Compute cosine similarity
        import numpy as np

        similarity = float(
            np.dot(baseline_emb, candidate_emb)
            / (np.linalg.norm(baseline_emb) * np.linalg.norm(candidate_emb))
        )

        if similarity >= similarity_threshold:
            return True, f"Semantic similarity {similarity:.3f} >= {similarity_threshold}", similarity
        elif similarity >= 0.85:
            # WARN level (not hard fail)
            return True, f"Semantic similarity {similarity:.3f} WARN (below {similarity_threshold})", similarity
        else:
            return False, f"Semantic similarity {similarity:.3f} < 0.85 (FAIL)", similarity

    except ImportError:
        return False, "sentence-transformers not installed; cannot perform semantic check", 0.0
    except Exception as e:
        return False, f"Semantic check error: {str(e)}", 0.0
