#!/usr/bin/env python3
"""Avaliação de threshold via curva Precision-Recall.

Roda o pipeline em todos os pares do data/labeled/pairs.csv,
calcula métricas para cada threshold candidato e plota a curva P-R,
identificando o ponto de operação ideal (melhor F1 com Recall >= 0.90).

Uso:
    python scripts/evaluate_threshold.py
    python scripts/evaluate_threshold.py --pairs-csv data/labeled/pairs.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Raiz do projeto e src/ no path — independente do CWD
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fusion.decision import fuse_and_decide
from preprocessing.image_loader import load_and_preprocess_image
from similarity.orb import compute_orb_score
from similarity.ssim import compute_ssim_score


def score_pair(ref_path: str, insp_path: str) -> tuple[float, float, float]:
    """Retorna (ssim_score, orb_score, final_score) para um par."""
    try:
        import tensorflow as tf  # noqa: PLC0415
        ref_arg = tf.constant(ref_path)
        cur_arg = tf.constant(insp_path)
    except ModuleNotFoundError:
        ref_arg = ref_path
        cur_arg = insp_path

    img_ref = load_and_preprocess_image(ref_arg)
    img_cur = load_and_preprocess_image(cur_arg)

    # Compatível com TF tensor e numpy array
    img_ref_np = img_ref.numpy() if hasattr(img_ref, "numpy") else np.asarray(img_ref)
    img_cur_np = img_cur.numpy() if hasattr(img_cur, "numpy") else np.asarray(img_cur)

    ssim_s = float(compute_ssim_score(img_ref_np, img_cur_np))
    orb_s = compute_orb_score(img_ref_np, img_cur_np)
    final_s, _ = fuse_and_decide(ssim_s, orb_s)
    return ssim_s, orb_s, final_s


def evaluate(pairs_csv: Path, min_recall: float, out_dir: Path) -> None:
    df = pd.read_csv(pairs_csv)
    required = {"ref_path", "insp_path", "label"}
    if not required.issubset(df.columns):
        raise ValueError(f"pairs.csv deve ter colunas: {required}")

    print(f"📊 Avaliando {len(df)} pares...\n")

    scores: list[float] = []
    labels: list[int] = []

    for i, row in df.iterrows():
        _, _, final_s = score_pair(row["ref_path"], row["insp_path"])
        scores.append(final_s)
        labels.append(int(row["label"]))
        status = "🔴 dano" if row["label"] == 1 else "🟢 ok  "
        print(f"  [{int(i)+1:03d}] {status} | final={final_s:.4f}")

    scores_arr = np.array(scores)
    labels_arr = np.array(labels)

    # anomaly_score = 1 - final_score (score alto = similar = sem dano)
    anomaly = 1.0 - scores_arr

    from sklearn.metrics import (  # noqa: PLC0415
        average_precision_score,
        precision_recall_curve,
    )

    precision, recall, thresholds = precision_recall_curve(labels_arr, anomaly)
    ap = average_precision_score(labels_arr, anomaly)

    # F1 por threshold
    f1 = 2 * precision * recall / (precision + recall + 1e-8)

    # Ponto ideal: máximo F1 com Recall >= min_recall
    valid = recall >= min_recall
    if valid.any():
        best_idx = int(np.argmax(np.where(valid, f1, 0.0)))
    else:
        best_idx = int(np.argmax(f1))

    # threshold em anomaly space → converter para decision threshold
    best_anomaly_t = thresholds[best_idx] if best_idx < len(thresholds) else thresholds[-1]
    best_decision_t = float(1.0 - best_anomaly_t)

    print(f"\n{'─'*55}")
    print(f"  Average Precision (AP): {ap:.3f}")
    print(f"  Melhor threshold sugerido: DECISION_THRESHOLD = {best_decision_t:.3f}")
    print(f"  Precision : {precision[best_idx]:.3f}")
    print(f"  Recall    : {recall[best_idx]:.3f}")
    print(f"  F1        : {f1[best_idx]:.3f}")
    print(f"{'─'*55}")
    print(f"\n  → Atualize src/config.py: DECISION_THRESHOLD = {best_decision_t:.2f}\n")

    # ─── Plot ─────────────────────────────────────────────────────────────────
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5))

    ax.plot(recall, precision, marker=".", linewidth=1.5, label=f"AP = {ap:.2f}")
    ax.scatter(
        recall[best_idx], precision[best_idx],
        color="red", zorder=5, s=100,
        label=f"Best F1={f1[best_idx]:.2f} (T={best_decision_t:.2f})",
    )
    ax.axvline(min_recall, color="gray", linestyle="--", linewidth=0.8,
               label=f"Recall mínimo = {min_recall:.0%}")

    ax.set_xlabel("Recall  (sensibilidade — detecta danos reais)")
    ax.set_ylabel("Precision  (evita alarmes falsos)")
    ax.set_title("Curva Precision-Recall — Comparador de Aeronaves")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    out_path = out_dir / "pr_curve.png"
    fig.savefig(out_path, dpi=150)
    print(f"  📈 Curva salva em: {out_path}")
    plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description="Avaliação de threshold via curva P-R")
    parser.add_argument(
        "--pairs-csv",
        type=Path,
        default=PROJECT_ROOT / "data/labeled/pairs.csv",
        help="CSV com colunas ref_path, insp_path, label",
    )
    parser.add_argument(
        "--min-recall",
        type=float,
        default=0.90,
        help="Recall mínimo aceitável (padrão: 0.90 para inspeção aeronáutica)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PROJECT_ROOT / "reports",
        help="Diretório para salvar gráfico e relatório",
    )
    args = parser.parse_args()

    if not args.pairs_csv.exists():
        print(f"❌ pairs.csv não encontrado: {args.pairs_csv}")
        print("   Execute primeiro: python scripts/generate_synthetic_data.py")
        sys.exit(1)

    evaluate(args.pairs_csv, args.min_recall, args.out_dir)


if __name__ == "__main__":
    main()
