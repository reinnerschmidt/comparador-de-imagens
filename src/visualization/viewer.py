from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np


def _to_numpy(value):
    if hasattr(value, "numpy"):
        return value.numpy()
    return np.asarray(value)


def highlight_differences(image, diff_mask):
    """Destaca em vermelho as regioes com diferenca na imagem de inspecao."""
    alpha = 0.5

    image_np = _to_numpy(image).astype(np.float32)
    image_np = np.clip(image_np, 0.0, 1.0)

    mask_np = _to_numpy(diff_mask)
    if mask_np.ndim == 3 and mask_np.shape[-1] == 1:
        mask_np = np.squeeze(mask_np, axis=-1)
    mask_np = mask_np.astype(bool)

    highlighted = image_np.copy()
    red = np.array([1.0, 0.0, 0.0], dtype=np.float32)

    highlighted[mask_np] = (1.0 - alpha) * highlighted[mask_np] + alpha * red
    return np.clip(highlighted, 0.0, 1.0).astype(np.float32)


def show_comparison(img_ref, img_cur, diff_mask, ssim_score, orb_score, recommendation):
    img_ref_np = np.clip(_to_numpy(img_ref).astype(np.float32), 0.0, 1.0)
    highlighted_cur = highlight_differences(img_cur, diff_mask)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    axes[0].imshow(img_ref_np)
    axes[0].set_title("Referencia")
    axes[0].axis("off")

    axes[1].imshow(highlighted_cur)
    axes[1].set_title("Inspecao (com destaques)")
    axes[1].axis("off")

    fig.suptitle(
        f"SSIM: {float(ssim_score):.4f} | ORB: {float(orb_score):.4f}\n{recommendation}",
        fontsize=11,
    )
    fig.tight_layout()
    plt.show()

    print(f"SSIM score: {float(ssim_score):.4f}")
    print(f"ORB score: {float(orb_score):.4f}")
    print(f"Recommendation: {recommendation}")

    return fig
