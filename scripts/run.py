#!/usr/bin/env python3
"""Pipeline de inspeção — processa todos os pares de imagens em data/load/.

Estrutura de entrada esperada:
    data/load/
    ├── before/     ← imagens de referência (foto "antes")
    └── after/      ← imagens de inspeção   (foto "depois")

    Arquivos com o MESMO NOME em before/ e after/ formam um par.
    Exemplo: before/asa_esquerda.jpg  +  after/asa_esquerda.jpg

Saída gerada automaticamente:
    reports/
    ├── comparisons/
    │   ├── asa_esquerda.png   ← visualização lado a lado com diferenças
    │   └── ...
    └── summary.csv            ← resumo de todos os pares com scores e diagnóstico

    Pares processados também são copiados para:
    data/reference/   e   data/inspection/

Uso:
    python3 scripts/run.py
    python3 scripts/run.py --load-dir data/load --no-move
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from datetime import datetime
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")  # sem janela — roda em qualquer ambiente
import matplotlib.pyplot as plt
import numpy as np

# Adiciona src/ ao path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import DECISION_THRESHOLD
from fusion.decision import fuse_and_decide
from preprocessing.image_loader import _load_with_cv2
from similarity.embedding import _HAS_TF, compute_damage_heatmap, compute_embedding_score
from similarity.orb import compute_orb_score
from similarity.ssim import compute_diff_mask

# ─── Raiz do projeto (sempre relativo ao script, independente do CWD) ─────────
PROJECT_ROOT = Path(__file__).parent.parent

# ─── Constantes de pastas ─────────────────────────────────────────────────────
LOAD_BEFORE     = PROJECT_ROOT / "data/load/before"
LOAD_AFTER      = PROJECT_ROOT / "data/load/after"
OUT_COMPARISONS = PROJECT_ROOT / "reports/comparisons"
OUT_REFERENCE   = PROJECT_ROOT / "data/reference"
OUT_INSPECTION  = PROJECT_ROOT / "data/inspection"
OUT_SUMMARY     = PROJECT_ROOT / "reports/summary.csv"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}


# ─── Utilitários ──────────────────────────────────────────────────────────────

def _find_pairs(before_dir: Path, after_dir: Path) -> list[tuple[Path, Path]]:
    """Encontra arquivos com mesmo nome nas duas pastas."""
    before_files = {f.name: f for f in before_dir.iterdir()
                    if f.suffix.lower() in IMAGE_EXTENSIONS}
    after_files  = {f.name: f for f in after_dir.iterdir()
                    if f.suffix.lower() in IMAGE_EXTENSIONS}

    common = sorted(set(before_files) & set(after_files))
    only_before = sorted(set(before_files) - set(after_files))
    only_after  = sorted(set(after_files)  - set(before_files))

    if only_before:
        print(f"   [AVISO] Sem par em after/: {', '.join(only_before)}")
    if only_after:
        print(f"   [AVISO] Sem par em before/: {', '.join(only_after)}")

    return [(before_files[name], after_files[name]) for name in common]


def _save_comparison(
    img_ref: np.ndarray,
    img_cur: np.ndarray,
    emb_score: float,
    orb_score: float,
    final_score: float,
    alarme: bool,
    out_path: Path,
) -> None:
    """Salva visualização lado a lado: referência / inspeção / heatmap de dano."""
    h, w = img_cur.shape[:2]

    if _HAS_TF:
        # Heatmap semântico via diferença de features CNN
        heatmap = compute_damage_heatmap(img_ref, img_cur, h, w)  # [H, W] float [0,1]
        cmap    = plt.get_cmap('jet')
        heat_rgb = cmap(heatmap)[..., :3].astype(np.float32)      # [H, W, 3]
        overlay  = np.clip(0.55 * img_cur + 0.45 * heat_rgb, 0.0, 1.0)
        map_title = "Heatmap de diferença (CNN)"
    else:
        # Fallback: overlay vermelho por pixel diff
        diff_mask = np.asarray(compute_diff_mask(img_ref, img_cur))
        if diff_mask.ndim == 3:
            mask_2d = diff_mask[:, :, 0].astype(bool)
        else:
            mask_2d = diff_mask.astype(bool)
        overlay = img_cur.copy()
        red = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        overlay[mask_2d] = 0.5 * overlay[mask_2d] + 0.5 * red
        overlay = np.clip(overlay, 0.0, 1.0)
        map_title = "Diferenças pixel (fallback)"

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    axes[0].imshow(img_ref)
    axes[0].set_title("Referencia (before)", fontsize=12, fontweight="bold")
    axes[0].axis("off")

    axes[1].imshow(img_cur)
    axes[1].set_title("Inspecao (after)", fontsize=12, fontweight="bold")
    axes[1].axis("off")

    axes[2].imshow(overlay)
    axes[2].set_title(map_title, fontsize=12, fontweight="bold")
    axes[2].axis("off")

    status = "ALERTA: DIFERENCA DETECTADA" if alarme else "OK: SEM DIFERENCA SIGNIFICATIVA"
    fig.suptitle(
        f"{status}\n"
        f"Embedding={emb_score:.3f}  |  ORB={orb_score:.3f}  |  Final={final_score:.3f}"
        f"  |  Threshold={DECISION_THRESHOLD}",
        fontsize=11,
    )
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ─── Pipeline principal ───────────────────────────────────────────────────────

def run(load_dir: Path, move_files: bool) -> None:
    before_dir = load_dir / "before"
    after_dir  = load_dir / "after"

    # Verificar pastas de entrada
    if not before_dir.exists() or not after_dir.exists():
        print("\n[ERRO] Estrutura de pastas esperada:\n")
        print(f"    {load_dir}/")
        print(f"    ├── before/     <- imagens de referencia (foto anterior)")
        print(f"    └── after/      <- imagens de inspecao   (foto atual)\n")
        print("Crie as pastas e adicione as imagens com o MESMO NOME nos dois lados.")
        print(f"\nExemplo:")
        print(f"    {load_dir}/before/asa.jpg")
        print(f"    {load_dir}/after/asa.jpg\n")
        sys.exit(1)

    pairs = _find_pairs(before_dir, after_dir)

    if not pairs:
        print(f"\n[AVISO] Nenhum par encontrado em {load_dir}/before/ e {load_dir}/after/")
        print("Certifique-se de que os arquivos tem o MESMO NOME nas duas pastas.\n")
        sys.exit(0)

    print(f"\n   {len(pairs)} par(es) encontrado(s)\n")
    print(f"   {'Arquivo':<30} {'Embed':>6} {'ORB':>6} {'Final':>6}  Resultado")
    print(f"   {'-'*70}")

    summary_rows: list[dict] = []
    n_ok = 0
    n_alerta = 0

    for ref_path, insp_path in pairs:
        stem = ref_path.stem

        # Carregar
        img_ref = _load_with_cv2(str(ref_path))
        img_cur = _load_with_cv2(str(insp_path))

        # Métricas
        emb_score   = compute_embedding_score(img_ref, img_cur)
        orb_score   = compute_orb_score(img_ref, img_cur)
        final_score, recommendation = fuse_and_decide(emb_score, orb_score)
        alarme      = final_score < DECISION_THRESHOLD

        # Salvar comparação visual
        out_img = OUT_COMPARISONS / f"{stem}.png"
        _save_comparison(
            img_ref, img_cur,
            emb_score, orb_score, final_score, alarme,
            out_img,
        )

        # Copiar para data/reference e data/inspection
        if move_files:
            OUT_REFERENCE.mkdir(parents=True, exist_ok=True)
            OUT_INSPECTION.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ref_path,  OUT_REFERENCE  / ref_path.name)
            shutil.copy2(insp_path, OUT_INSPECTION / insp_path.name)

        status_str = "[ALERTA]" if alarme else "[OK]    "
        print(f"   {ref_path.name:<30} {emb_score:>6.3f} {orb_score:>6.3f} {final_score:>6.3f}  {status_str}")

        summary_rows.append({
            "arquivo":      ref_path.name,
            "embedding":    f"{emb_score:.4f}",
            "orb":          f"{orb_score:.4f}",
            "final_score":  f"{final_score:.4f}",
            "threshold":    DECISION_THRESHOLD,
            "alarme":       "SIM" if alarme else "NAO",
            "diagnostico":  recommendation,
            "comparacao":   str(out_img),
            "processado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

        if alarme:
            n_alerta += 1
        else:
            n_ok += 1

    # Salvar CSV de resumo
    OUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    write_header = not OUT_SUMMARY.exists()
    with open(OUT_SUMMARY, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        if write_header:
            writer.writeheader()
        writer.writerows(summary_rows)

    # Resumo final
    print(f"\n   {'─'*70}")
    print(f"   RESULTADO FINAL: {n_ok} OK  |  {n_alerta} ALERTAS  de {len(pairs)} pares")
    print(f"\n   Comparacoes visuais : {OUT_COMPARISONS}/")
    print(f"   Resumo CSV          : {OUT_SUMMARY}")
    if move_files:
        print(f"   Imagens arquivadas  : {OUT_REFERENCE}/  e  {OUT_INSPECTION}/")
    print()


def _create_example_structure(load_dir: Path) -> None:
    """Cria a estrutura de pastas de exemplo se não existir."""
    (load_dir / "before").mkdir(parents=True, exist_ok=True)
    (load_dir / "after").mkdir(parents=True, exist_ok=True)
    print(f"\n   Pastas criadas:")
    print(f"   {load_dir}/before/   <- coloque as imagens de referencia aqui")
    print(f"   {load_dir}/after/    <- coloque as imagens de inspecao aqui\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline de inspeção — processa todos os pares em data/load/"
    )
    parser.add_argument(
        "--load-dir",
        type=Path,
        default=PROJECT_ROOT / "data/load",
        help="Pasta de entrada com subpastas before/ e after/",
    )
    parser.add_argument(
        "--no-move",
        action="store_true",
        help="Nao arquivar imagens em data/reference/ e data/inspection/",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Cria a estrutura de pastas data/load/before/ e data/load/after/",
    )
    args = parser.parse_args()

    print("\n" + "=" * 72)
    print("   COMPARADOR DE IMAGENS DE AERONAVE  —  Pipeline de Inspecao")
    print("=" * 72)

    if args.init:
        _create_example_structure(args.load_dir)
        return

    run(args.load_dir, move_files=not args.no_move)


if __name__ == "__main__":
    main()
