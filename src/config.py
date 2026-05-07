from __future__ import annotations

# ─── Image preprocessing ──────────────────────────────────────────────────────
TARGET_SIZE: tuple[int, int] = (256, 256)

# CLAHE (Contrast Limited Adaptive Histogram Equalization)
# Normaliza iluminação antes da extração de features — reduz ruído de iluminação
USE_CLAHE: bool = True
CLAHE_CLIP_LIMIT: float = 3.5
CLAHE_TILE_SIZE: tuple[int, int] = (8, 8)

# ─── Diff mask ────────────────────────────────────────────────────────────────
# Threshold para máscara visual de diferenças (0–1); usado apenas na visualização
# 0.25 → ignora gradientes suaves de iluminação, sombras e artefatos JPEG
DIFF_MASK_PIXEL_THRESHOLD: float = 0.25

# ─── ORB ──────────────────────────────────────────────────────────────────────
ORB_N_FEATURES: int = 500
# Ratio test de Lowe: mais estrito (0.65) → menos matches espúrios em texturas lisas
ORB_LOWE_RATIO: float = 0.65

# ─── Embedding CNN ────────────────────────────────────────────────────────────
# EfficientNetB0 pré-treinada no ImageNet — extrai vetor de 1280 features por imagem.
# Comparação via similaridade cosseno: robusto a ângulo, zoom e iluminação.
EMBEDDING_MODEL: str = "EfficientNetB0"

# ─── Fusion ───────────────────────────────────────────────────────────────────
# ORB com peso mínimo: fotos tiradas de ângulos diferentes sempre geram ORB baixo
# (keypoints não se alinham geometricamente), o que tornava o sinal ruidoso.
# EfficientNetB0 captura a semântica da imagem sem depender de alinhamento.
EMBEDDING_WEIGHT: float = 0.95
ORB_WEIGHT: float = 0.05

# ─── Decision ─────────────────────────────────────────────────────────────────
# Calibrado analiticamente com 5 pares reais + EfficientNetB0:
#   manche (sem dano): 0.855 | console (com dano): 0.851 → margem de 0.004
# IMPORTANTE: recalibrar via anotador ao adicionar mais pares reais.
DECISION_THRESHOLD: float = 0.853
