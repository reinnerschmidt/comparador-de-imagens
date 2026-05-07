"""analyzer.py — Wrapper do pipeline IA chamado pela API.

Expõe analyze_pair() para uso direto pelo server.py sem depender
da interface CLI do pipeline.py.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from preprocessing.image_loader import _load_with_cv2
from similarity import embedding, orb
from fusion import decision


def analyze_pair(before_path: str, after_path: str, comp_dir: str) -> dict:
    """Analisa um par BEFORE/AFTER e salva o heatmap.

    Args:
        before_path: Caminho absoluto da foto BEFORE.
        after_path:  Caminho absoluto da foto AFTER.
        comp_dir:    Diretório onde o heatmap será salvo.

    Returns:
        dict com emb_score, orb_score, final_score, status, heatmap_path.
    """
    img_ref = _load_with_cv2(before_path)
    img_cur = _load_with_cv2(after_path)

    emb_score  = embedding.compute_embedding_score(img_ref, img_cur)
    orb_score  = orb.compute_orb_score(img_ref, img_cur)
    final_score, recommendation = decision.fuse_and_decide(emb_score, orb_score)

    heatmap_path = _save_heatmap(img_ref, img_cur, before_path, comp_dir)

    return {
        "emb_score":    round(emb_score,   4),
        "orb_score":    round(orb_score,   4),
        "final_score":  round(final_score, 4),
        "status":       "OK" if "Nenhuma" in recommendation else "DIFERENCA",
        "recommendation": recommendation,
        "heatmap_path": heatmap_path,
    }


def _save_heatmap(
    img_ref: np.ndarray,
    img_cur: np.ndarray,
    source_name: str,
    comp_dir: str,
) -> str | None:
    """Gera imagem lado a lado: Antes | Depois | Mapa de Calor."""
    try:
        h, w = img_ref.shape[:2]

        # Heatmap semântico se TF disponível, senão diferença pixel a pixel
        try:
            from similarity.embedding import compute_damage_heatmap, _HAS_TF
            heatmap = compute_damage_heatmap(img_ref, img_cur, h, w) if _HAS_TF else None
        except Exception:
            heatmap = None

        if heatmap is None:
            heatmap = np.mean(np.abs(img_ref - img_cur), axis=-1)
            d_min, d_max = heatmap.min(), heatmap.max()
            heatmap = (heatmap - d_min) / (d_max - d_min + 1e-8)

        heatmap_color = cv2.applyColorMap(
            (heatmap * 255).astype(np.uint8), cv2.COLORMAP_JET
        )
        heatmap_color = cv2.cvtColor(heatmap_color, cv2.COLOR_BGR2RGB)

        ref_u8    = (img_ref * 255).astype(np.uint8)
        cur_u8    = (img_cur * 255).astype(np.uint8)
        composite = np.concatenate([ref_u8, cur_u8, heatmap_color], axis=1)

        ts      = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        stem    = Path(source_name).stem
        out_dir = Path(comp_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{stem}_{ts}_heatmap.jpg"

        cv2.imwrite(str(out_path), cv2.cvtColor(composite, cv2.COLOR_RGB2BGR))
        return str(out_path)
    except Exception as e:
        print(f"[analyzer] Falha ao gerar heatmap: {e}")
        return None
