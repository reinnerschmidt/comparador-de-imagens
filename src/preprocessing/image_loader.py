from __future__ import annotations

import cv2
import numpy as np

try:
    import tensorflow as tf
    _HAS_TF = True
except ModuleNotFoundError:
    _HAS_TF = False

from config import CLAHE_CLIP_LIMIT, CLAHE_TILE_SIZE, TARGET_SIZE, USE_CLAHE


def _apply_clahe(image_np: np.ndarray) -> np.ndarray:
    """Equalização adaptativa de histograma no espaço LAB (canal L apenas).

    Aplicar CLAHE em ambas as imagens antes da comparação neutraliza
    variações globais de iluminação, reduzindo falsos positivos de inspeção.
    """
    lab = cv2.cvtColor(image_np, cv2.COLOR_RGB2LAB)
    clahe = cv2.createCLAHE(
        clipLimit=CLAHE_CLIP_LIMIT,
        tileGridSize=CLAHE_TILE_SIZE,
    )
    lab[:, :, 0] = clahe.apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)


def _load_with_cv2(path: str) -> np.ndarray:
    """Carrega imagem com OpenCV e retorna float32 [0, 1] RGB."""
    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(f"Imagem não encontrada: {path}")
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (TARGET_SIZE[1], TARGET_SIZE[0]))
    img = img.astype(np.float32) / 255.0
    if USE_CLAHE:
        uint8 = (img * 255).astype(np.uint8)
        img = _apply_clahe(uint8).astype(np.float32) / 255.0
    return img


def _clahe_tf_wrapper(image: np.ndarray) -> np.ndarray:
    """Wrapper para rodar CLAHE (OpenCV) dentro de tf.numpy_function.
    
    Nota: dentro de tf.numpy_function o argumento JÁ é um np.ndarray,
    portanto não se deve chamar .numpy() sobre ele.
    """
    uint8_img = (np.clip(image, 0.0, 1.0) * 255).astype(np.uint8)
    result = _apply_clahe(uint8_img)
    return result.astype(np.float32) / 255.0


def load_and_preprocess_image(path) -> "tf.Tensor | np.ndarray":
    """Carrega imagem do disco, redimensiona para TARGET_SIZE e normaliza [0, 1].

    Usa TensorFlow quando disponível (pipeline completo com AUTOTUNE).
    Cai para OpenCV/numpy quando TF não está instalado (scripts de avaliação).
    Se USE_CLAHE=True, aplica equalização adaptativa de histograma para
    robustez a variações de iluminação entre referência e inspeção.
    """
    if not _HAS_TF:
        path_str = path.numpy().decode("utf-8") if hasattr(path, "numpy") else str(path)
        return _load_with_cv2(path_str)

    image_bytes = tf.io.read_file(path)
    image = tf.image.decode_image(
        image_bytes, channels=3, expand_animations=False
    )
    image = tf.image.resize(image, list(TARGET_SIZE))
    image = tf.image.convert_image_dtype(image, tf.float32)

    if USE_CLAHE:
        image = tf.numpy_function(
            _clahe_tf_wrapper,
            [image],
            tf.float32,
        )
        image.set_shape((*TARGET_SIZE, 3))

    return image
