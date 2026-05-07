#!/usr/bin/env python3
"""Comparação direta entre duas imagens de aeronave.

Uso:
    python scripts/compare.py referencia.jpg inspecao.jpg
    python scripts/compare.py referencia.jpg inspecao.jpg --show
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# Adiciona src/ ao path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import DECISION_THRESHOLD
from fusion.decision import fuse_and_decide
from preprocessing.image_loader import _load_with_cv2
from similarity.embedding import backend, compute_embedding_score
from similarity.orb import compute_orb_score
from similarity.ssim import compute_diff_mask


def compare(ref_path: str, insp_path: str, show: bool = False, save: str | None = None) -> None:
    print(f"\n🛩️  Comparando imagens...\n")
    print(f"   Referência : {ref_path}")
    print(f"   Inspeção   : {insp_path}")
    print(f"   Backend    : {backend()}\n")

    # ─── Carregar ─────────────────────────────────────────────────────────────
    img_ref = _load_with_cv2(ref_path)
    img_cur = _load_with_cv2(insp_path)

    # ─── Calcular métricas ────────────────────────────────────────────────────
    emb_score  = compute_embedding_score(img_ref, img_cur)
    orb_score  = compute_orb_score(img_ref, img_cur)
    final_score, recommendation = fuse_and_decide(emb_score, orb_score)

    # Diff mask mantida apenas para visualização (não afeta a decisão)
    diff_mask  = np.asarray(compute_diff_mask(img_ref, img_cur))

    # ─── Resultado ────────────────────────────────────────────────────────────
    print(f"   Embedding  : {emb_score:.4f}  (similaridade semântica)")
    print(f"   ORB        : {orb_score:.4f}  (correspondência de features locais)")
    print(f"   Score final: {final_score:.4f}  (threshold atual: {DECISION_THRESHOLD})")
    print()

    alarme = final_score < DECISION_THRESHOLD
    if alarme:
        print(f"   [ALERTA] {recommendation}")
    else:
        print(f"   [OK]     {recommendation}")
    print()

    # ─── Visualização ─────────────────────────────────────────────────────────
    if show or save:
        if diff_mask.ndim == 3:
            mask_2d = diff_mask[:, :, 0].astype(bool)
        else:
            mask_2d = diff_mask.astype(bool)

        # Overlay vermelho sobre imagem de inspeção
        highlighted = img_cur.copy()
        red = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        highlighted[mask_2d] = 0.5 * highlighted[mask_2d] + 0.5 * red
        highlighted = np.clip(highlighted, 0.0, 1.0)

        fig, axes = plt.subplots(1, 3, figsize=(15, 5))

        axes[0].imshow(img_ref)
        axes[0].set_title("Referência", fontsize=12)
        axes[0].axis("off")

        axes[1].imshow(img_cur)
        axes[1].set_title("Inspeção", fontsize=12)
        axes[1].axis("off")

        axes[2].imshow(highlighted)
        axes[2].set_title("Diferenças destacadas (pixel-diff)", fontsize=12)
        axes[2].axis("off")

        status = "[ALERTA] DIFERENCA DETECTADA" if alarme else "[OK] SEM DIFERENCA SIGNIFICATIVA"
        fig.suptitle(
            f"{status}\n"
            f"Embedding={emb_score:.3f} | ORB={orb_score:.3f} | Final={final_score:.3f}",
            fontsize=11,
        )
        fig.tight_layout()

        if save:
            out_path = Path(save)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(out_path, dpi=150, bbox_inches="tight")
            print(f"   💾 Comparação salva em: {out_path}")

        if show:
            plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compara duas imagens de aeronave e detecta diferenças"
    )
    parser.add_argument("referencia",  help="Caminho para a imagem de referência (antes)")
    parser.add_argument("inspecao",    help="Caminho para a imagem de inspeção (depois)")
    parser.add_argument("--show",      action="store_true", help="Exibir visualização")
    parser.add_argument("--save",      metavar="ARQUIVO",   help="Salvar comparação em arquivo PNG")
    args = parser.parse_args()

    for p in [args.referencia, args.inspecao]:
        if not Path(p).exists():
            print(f"❌ Arquivo não encontrado: {p}")
            sys.exit(1)

    compare(args.referencia, args.inspecao, show=args.show, save=args.save)


if __name__ == "__main__":
    main()
