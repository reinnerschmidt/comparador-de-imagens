from __future__ import annotations

import cv2
import numpy as np

from config import ORB_LOWE_RATIO, ORB_N_FEATURES


def _to_uint8_numpy(image) -> np.ndarray:
    """Converte tensor/array de imagem para numpy uint8 [0, 255]."""
    if hasattr(image, "numpy"):
        image = image.numpy()
    image = np.asarray(image)
    if image.dtype != np.uint8:
        image = np.clip(image, 0.0, 1.0)
        image = (image * 255.0).astype(np.uint8)
    return image


def compute_orb_score(img_ref, img_cur) -> float:
    """Calcula score ORB usando ratio test de Lowe (match_ratio sobre total de keypoints).

    Retorna 0.0 quando não há keypoints (superfície lisa) — o módulo de
    fusão trata esse caso como fallback para SSIM puro.
    """
    ref_np = _to_uint8_numpy(img_ref)
    cur_np = _to_uint8_numpy(img_cur)

    ref_gray = cv2.cvtColor(ref_np, cv2.COLOR_RGB2GRAY) if ref_np.ndim == 3 else ref_np
    cur_gray = cv2.cvtColor(cur_np, cv2.COLOR_RGB2GRAY) if cur_np.ndim == 3 else cur_np

    orb = cv2.ORB_create(nfeatures=ORB_N_FEATURES)
    kp_ref, desc_ref = orb.detectAndCompute(ref_gray, None)
    kp_cur, desc_cur = orb.detectAndCompute(cur_gray, None)

    if not kp_ref or not kp_cur or desc_ref is None or desc_cur is None:
        return 0.0

    # knnMatch k=2 + ratio test de Lowe — descarta matches ambíguos
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    try:
        raw_matches = bf.knnMatch(desc_ref, desc_cur, k=2)
    except cv2.error:
        return 0.0

    good = [
        m for pair in raw_matches
        if len(pair) == 2
        for m, n in [pair]
        if m.distance < ORB_LOWE_RATIO * n.distance
    ]

    # Normaliza pelo maior conjunto de keypoints (penaliza matches escassos)
    total_kp = max(len(kp_ref), len(kp_cur))
    match_ratio = len(good) / total_kp
    return float(np.clip(match_ratio, 0.0, 1.0))
