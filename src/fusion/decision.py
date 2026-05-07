from __future__ import annotations

from config import DECISION_THRESHOLD, EMBEDDING_WEIGHT, ORB_WEIGHT


def fuse_and_decide(
    primary_score: float,
    orb_score: float,
) -> tuple[float, str]:
    """Combina embedding similarity e ORB numa decisão binária.

    Fallback: quando ORB = 0.0 (superfície lisa sem keypoints detectáveis),
    o score final é determinado exclusivamente pelo embedding, evitando que a
    ausência de features locais penalize indevidamente a decisão.

    Args:
        primary_score: Cosine similarity entre embeddings CNN (0–1, alto = similar).
        orb_score:     Match ratio ORB (0–1, alto = estrutura local preservada).

    Returns:
        (final_score, recommendation) onde final_score < DECISION_THRESHOLD → dano.
    """
    primary_val = float(primary_score)
    orb_val     = float(orb_score)

    if orb_val == 0.0:
        final_score = primary_val
    else:
        final_score = EMBEDDING_WEIGHT * primary_val + ORB_WEIGHT * orb_val

    recommendation = (
        "Diferença detectada - Inspeção manual recomendada"
        if final_score < DECISION_THRESHOLD
        else "Nenhuma diferença significativa detectada"
    )
    return final_score, recommendation
