"""CNN embedding similarity with automatic fallback.

Strategy selection (automatic):
    TensorFlow available → EfficientNetB0 ImageNet embeddings (best)
    TF not available     → HOG descriptor + cosine similarity (good fallback)

Both strategies return a score in [0, 1] where:
    1.0 = images are semantically identical  (no damage)
    0.0 = images are completely unrelated    (high damage probability)

Advantages over SSIM:
    - Robust to camera angle, zoom and framing differences
    - Robust to lighting and color variations
    - Understands visual semantics (not just pixel values)
"""
from __future__ import annotations

import numpy as np

try:
    import tensorflow as tf
    from tensorflow.keras import applications as _tf_apps
    _HAS_TF = True
except ModuleNotFoundError:
    _HAS_TF = False

# ─── TensorFlow path: EfficientNetB0 ─────────────────────────────────────────

_extractor: "tf.keras.Model | None" = None          # GlobalAvgPool → [1280]
_feat_extractor: "tf.keras.Model | None" = None    # mapa espacial  → [H, W, 1280]


def _get_extractor():
    global _extractor
    if _extractor is None:
        base = _tf_apps.EfficientNetB0(
            include_top=False,
            weights="imagenet",
            pooling="avg",         # → [batch, 1280]
            input_shape=(None, None, 3),
        )
        base.trainable = False
        _extractor = base
    return _extractor


def _get_feat_extractor():
    """Modelo que retorna mapas espaciais (sem GlobalAvgPool) para o heatmap."""
    global _feat_extractor
    if _feat_extractor is None:
        base = _tf_apps.EfficientNetB0(
            include_top=False,
            weights="imagenet",
            pooling=None,          # mantém dimensões espaciais → [H_feat, W_feat, C]
            input_shape=(None, None, 3),
        )
        base.trainable = False
        _feat_extractor = base
    return _feat_extractor


def _compute_cnn(img_ref, img_cur) -> float:
    """Cosine similarity between EfficientNetB0 embeddings."""
    extractor = _get_extractor()

    # EfficientNetB0 expects [0, 255]
    ref = _tf_apps.efficientnet.preprocess_input(
        tf.cast(img_ref, tf.float32) * 255.0
    )
    cur = _tf_apps.efficientnet.preprocess_input(
        tf.cast(img_cur, tf.float32) * 255.0
    )

    emb_ref = extractor(tf.expand_dims(ref, 0), training=False)  # [1, 1280]
    emb_cur = extractor(tf.expand_dims(cur, 0), training=False)

    emb_ref = tf.nn.l2_normalize(emb_ref, axis=-1)
    emb_cur = tf.nn.l2_normalize(emb_cur, axis=-1)
    return float(np.clip(float(tf.reduce_sum(emb_ref * emb_cur)), 0.0, 1.0))


def compute_damage_heatmap(
    img_ref,
    img_cur,
    out_h: int,
    out_w: int,
) -> np.ndarray:
    """Mapa de calor de dano usando diferença de features espaciais CNN.

    Extrai os mapas de ativação da última camada convolucional para cada imagem
    e calcula a diferença média por posição espacial. Regioes com maior
    ativação diferencial são semanticamente diferentes entre as imagens.

    Args:
        img_ref: Imagem de referência, float32 [H, W, 3] em [0, 1].
        img_cur: Imagem de inspeção,   float32 [H, W, 3] em [0, 1].
        out_h: Altura do heatmap de saída.
        out_w: Largura do heatmap de saída.

    Returns:
        Heatmap normalizado em [0, 1], shape [out_h, out_w].
        0.0 = sem diferença semântica | 1.0 = máxima diferença
    """
    import cv2

    extractor = _get_feat_extractor()

    ref = _tf_apps.efficientnet.preprocess_input(
        tf.cast(img_ref, tf.float32) * 255.0
    )
    cur = _tf_apps.efficientnet.preprocess_input(
        tf.cast(img_cur, tf.float32) * 255.0
    )

    # Mapas espaciais: [1, H_feat, W_feat, 1280]
    feat_ref = extractor(tf.expand_dims(ref, 0), training=False)
    feat_cur = extractor(tf.expand_dims(cur, 0), training=False)

    # Normaliza por canal para invariancia de magnitude
    feat_ref = tf.nn.l2_normalize(feat_ref, axis=-1)
    feat_cur = tf.nn.l2_normalize(feat_cur, axis=-1)

    # Diferença L2 por localização espacial, media sobre canais → [H_feat, W_feat]
    diff = tf.reduce_mean(tf.square(feat_ref - feat_cur), axis=-1)
    diff = tf.squeeze(diff, 0).numpy()

    # Normaliza para [0, 1]
    d_min, d_max = diff.min(), diff.max()
    if d_max > d_min:
        diff = (diff - d_min) / (d_max - d_min)

    # Upsample para o tamanho original da imagem
    heatmap = cv2.resize(diff.astype(np.float32), (out_w, out_h),
                         interpolation=cv2.INTER_CUBIC)
    return np.clip(heatmap, 0.0, 1.0)


# ─── Fallback path: HOG + cosine similarity ───────────────────────────────────

def _hog_descriptor(img_np: np.ndarray) -> np.ndarray:
    """HOG features over a [H, W, 3] float32 [0, 1] image.

    HOG (Histogram of Oriented Gradients) captures local edge structure,
    making it robust to lighting changes and moderate viewpoint shifts.
    """
    from skimage.feature import hog  # always available — listed in pyproject.toml

    features = hog(
        img_np,
        orientations=9,
        pixels_per_cell=(16, 16),
        cells_per_block=(2, 2),
        channel_axis=-1,
    )
    norm = np.linalg.norm(features)
    return features / (norm + 1e-8)


def _compute_hog(img_ref, img_cur) -> float:
    """Cosine similarity between HOG descriptors (no deep learning required)."""
    ref_np = np.asarray(img_ref, dtype=np.float32)
    cur_np = np.asarray(img_cur, dtype=np.float32)
    feat_ref = _hog_descriptor(ref_np)
    feat_cur = _hog_descriptor(cur_np)
    return float(np.clip(np.dot(feat_ref, feat_cur), 0.0, 1.0))


# ─── Public API ───────────────────────────────────────────────────────────────

def compute_embedding_score(img_ref, img_cur) -> float:
    """Semantic similarity score between two images.

    Automatically uses EfficientNetB0 when TensorFlow is available,
    otherwise falls back to HOG descriptor cosine similarity.

    Args:
        img_ref: Reference image, float32 [H, W, 3] in [0, 1].
        img_cur: Inspection image, float32 [H, W, 3] in [0, 1].

    Returns:
        Similarity in [0, 1]. Higher = more similar = less likely damaged.
    """
    if _HAS_TF:
        return _compute_cnn(img_ref, img_cur)
    return _compute_hog(img_ref, img_cur)


def backend() -> str:
    """Returns the active backend name for logging purposes."""
    return "EfficientNetB0 (TF)" if _HAS_TF else "HOG (scikit-image)"
