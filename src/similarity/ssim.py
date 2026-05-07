from __future__ import annotations

try:
    import tensorflow as tf
    _HAS_TF = True
except ModuleNotFoundError:
    _HAS_TF = False

import numpy as np
from skimage.metrics import structural_similarity as _ssim_sk

from config import DIFF_MASK_PIXEL_THRESHOLD


def compute_ssim_score(img_ref, img_cur) -> float:
    """Calcula o SSIM global entre duas imagens float32 no intervalo [0, 1].

    Usa tf.image.ssim quando TensorFlow está disponível; caso contrário,
    recorre ao skimage (útil em ambientes de teste sem TF instalado).
    """
    if _HAS_TF:
        img_ref = tf.cast(img_ref, tf.float32)
        img_cur = tf.cast(img_cur, tf.float32)
        return tf.cast(tf.image.ssim(img_ref, img_cur, max_val=1.0), tf.float32)

    # Fallback: skimage SSIM (sem TensorFlow)
    ref_np = np.asarray(img_ref, dtype=np.float32)
    cur_np = np.asarray(img_cur, dtype=np.float32)
    # SSIM multicanal
    score = _ssim_sk(ref_np, cur_np, data_range=1.0, channel_axis=-1)
    return float(score)


def compute_diff_mask(img_ref, img_cur) -> "np.ndarray | tf.Tensor":
    """Máscara de diferenças com suavização por average-pool para reduzir ruído de pixel.

    Usa diferença absoluta na escala de cinza + avg_pool 5×5 para eliminar
    pixels isolados causados por ruído de sensor, antes de aplicar o threshold.
    """
    if _HAS_TF:
        img_ref = tf.cast(img_ref, tf.float32)
        img_cur = tf.cast(img_cur, tf.float32)

        gray_ref = tf.image.rgb_to_grayscale(img_ref)  # [H, W, 1]
        gray_cur = tf.image.rgb_to_grayscale(img_cur)

        diff_map = tf.abs(gray_ref - gray_cur)          # [H, W, 1]

        diff_4d = tf.expand_dims(diff_map, 0)           # [1, H, W, 1]
        diff_4d = tf.nn.avg_pool2d(diff_4d, ksize=5, strides=1, padding="SAME")
        diff_map = tf.squeeze(diff_4d, 0)               # [H, W, 1]

        mask = diff_map > DIFF_MASK_PIXEL_THRESHOLD     # [H, W, 1] bool
        channels = tf.shape(img_cur)[-1]
        return tf.repeat(mask, repeats=channels, axis=-1)

    # Fallback numpy (sem TF)
    ref_np = np.asarray(img_ref, dtype=np.float32)
    cur_np = np.asarray(img_cur, dtype=np.float32)

    gray_ref = np.dot(ref_np[..., :3], [0.2989, 0.5870, 0.1140])
    gray_cur = np.dot(cur_np[..., :3], [0.2989, 0.5870, 0.1140])
    diff_map = np.abs(gray_ref - gray_cur)

    # Average blur 5×5 via separable convolution with uniform kernel
    from scipy.ndimage import uniform_filter  # lightweight, always available with skimage  # noqa: PLC0415
    diff_map = uniform_filter(diff_map, size=5)

    mask = diff_map > DIFF_MASK_PIXEL_THRESHOLD   # [H, W] bool
    return np.stack([mask] * ref_np.shape[-1], axis=-1)  # [H, W, C]
