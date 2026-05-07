"""Pipeline de inspeção de aeronaves — AeroInspect MVP.

Emparelhamento por nome de arquivo:
    data/load/before/IMG_0954.JPG  <->  data/load/after/IMG_0954.JPG

Saida:
    reports/comparisons/   -> imagem lado a lado (antes | depois | heatmap)
    reports/report_*.json  -> dados estruturados
    reports/report_*.pdf   -> relatorio executivo

Uso:
    python src/pipeline.py --reference-dir data/load/before --inspection-dir data/load/after
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np

_SRC = Path(__file__).parent
sys.path.insert(0, str(_SRC))

from fusion import decision
from preprocessing.image_loader import _load_with_cv2
from similarity import embedding, orb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


# --- Emparelhamento ----------------------------------------------------------

def _find_pairs(ref_dir: Path, ins_dir: Path) -> list[tuple[Path, Path]]:
    ref_files = {f.name: f for f in ref_dir.iterdir() if f.suffix.lower() in IMAGE_EXTS}
    ins_files = {f.name: f for f in ins_dir.iterdir() if f.suffix.lower() in IMAGE_EXTS}

    paired: list[tuple[Path, Path]] = []
    for name, ref_path in sorted(ref_files.items()):
        if name in ins_files:
            paired.append((ref_path, ins_files[name]))
        else:
            log.warning("Sem par de inspecao para: %s -- ignorado", name)

    for name in sorted(set(ins_files) - set(ref_files)):
        log.warning("Sem referencia para: %s -- ignorado", name)

    return paired


# --- Heatmap -----------------------------------------------------------------

def _save_comparison_image(
    img_ref: np.ndarray,
    img_cur: np.ndarray,
    name: str,
    comp_dir: Path,
) -> Path:
    """Gera imagem lado a lado: Antes | Depois | Mapa de Calor."""
    h, w = img_ref.shape[:2]

    try:
        from similarity.embedding import compute_damage_heatmap, _HAS_TF
        if _HAS_TF:
            heatmap = compute_damage_heatmap(img_ref, img_cur, h, w)
        else:
            raise ImportError
    except Exception:
        heatmap = np.mean(np.abs(img_ref - img_cur), axis=-1)
        d_min, d_max = heatmap.min(), heatmap.max()
        heatmap = (heatmap - d_min) / (d_max - d_min + 1e-8)

    heatmap_u8    = (heatmap * 255).astype(np.uint8)
    heatmap_color = cv2.applyColorMap(heatmap_u8, cv2.COLORMAP_JET)
    heatmap_color = cv2.cvtColor(heatmap_color, cv2.COLOR_BGR2RGB)

    ref_u8    = (img_ref * 255).astype(np.uint8)
    cur_u8    = (img_cur * 255).astype(np.uint8)
    composite = np.concatenate([ref_u8, cur_u8, heatmap_color], axis=1)

    out_path = comp_dir / f"{Path(name).stem}_comparison.jpg"
    cv2.imwrite(str(out_path), cv2.cvtColor(composite, cv2.COLOR_RGB2BGR))
    return out_path


# --- Analise de par ----------------------------------------------------------

def _analyze_pair(ref_path: Path, ins_path: Path, comp_dir: Path) -> dict:
    img_ref = _load_with_cv2(str(ref_path))
    img_cur = _load_with_cv2(str(ins_path))

    emb_score  = embedding.compute_embedding_score(img_ref, img_cur)
    orb_score  = orb.compute_orb_score(img_ref, img_cur)
    final_score, recommendation = decision.fuse_and_decide(emb_score, orb_score)

    comp_path = _save_comparison_image(img_ref, img_cur, ref_path.name, comp_dir)

    return {
        "reference":        str(ref_path),
        "inspection":       str(ins_path),
        "comparison_image": str(comp_path),
        "emb_score":        round(emb_score,   4),
        "orb_score":        round(orb_score,   4),
        "final_score":      round(final_score, 4),
        "status":           "OK" if "Nenhuma" in recommendation else "DIFERENCA",
        "recommendation":   recommendation,
    }


# --- PDF executivo -----------------------------------------------------------

def _generate_pdf(report: dict, pdf_path: Path) -> None:
    from matplotlib.backends.backend_pdf import PdfPages

    s         = report["summary"]
    results   = report["results"]
    ok_color  = "#3fb950"
    err_color = "#f85149"
    bg        = "#0d1117"
    text_main = "#e6edf3"
    text_sub  = "#7d8590"
    accent    = "#58a6ff"

    with PdfPages(str(pdf_path)) as pdf:
        # Capa
        fig = plt.figure(figsize=(11.7, 8.3))
        fig.patch.set_facecolor(bg)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")
        ax.text(0.5, 0.78, "AeroInspect",
                ha="center", fontsize=40, fontweight="bold", color=accent,
                transform=ax.transAxes)
        ax.text(0.5, 0.65, "Relatorio Executivo de Inspecao Visual",
                ha="center", fontsize=18, color=text_main, transform=ax.transAxes)
        ax.text(0.5, 0.53,
                f"Data: {report['generated_at'][:19].replace('T', ' ')}",
                ha="center", fontsize=13, color=text_sub, transform=ax.transAxes)
        ax.text(0.5, 0.46,
                f"Backend IA: {report['ai_backend']}",
                ha="center", fontsize=13, color=text_sub, transform=ax.transAxes)
        ax.text(0.5, 0.33,
                f"Integros: {s['ok']}    Diferencas: {s['damaged']}    Erros: {s['errors']}   /   Total: {s['total']}",
                ha="center", fontsize=14, color="#d29922", transform=ax.transAxes)
        pdf.savefig(fig, facecolor=bg)
        plt.close(fig)

        # Uma pagina por par
        for r in results:
            fig_pair = plt.figure(figsize=(11.7, 8.3))
            fig_pair.patch.set_facecolor(bg)

            status_color = ok_color if r.get("status") == "OK" else err_color
            verdict = r.get("recommendation", r.get("error", "ERRO"))

            fig_pair.suptitle(
                f"{Path(r['reference']).name}   |   {verdict}",
                fontsize=12, fontweight="bold", color=status_color, y=0.97,
            )

            comp_img_path = r.get("comparison_image")
            if comp_img_path and Path(comp_img_path).exists():
                gs   = gridspec.GridSpec(1, 3, figure=fig_pair,
                                         top=0.88, bottom=0.14,
                                         hspace=0.1, wspace=0.05)
                comp = plt.imread(comp_img_path)
                w3   = comp.shape[1] // 3

                for col, (title, slc) in enumerate(zip(
                    ["ANTES (Referencia)", "DEPOIS (Inspecao)", "Mapa de Calor"],
                    [comp[:, :w3], comp[:, w3:2*w3], comp[:, 2*w3:]],
                )):
                    ax = fig_pair.add_subplot(gs[0, col])
                    ax.imshow(slc)
                    ax.set_title(title, color=text_main, fontsize=10, pad=6)
                    ax.axis("off")
            else:
                ax = fig_pair.add_axes([0.1, 0.2, 0.8, 0.6])
                ax.text(0.5, 0.5, "Imagem de comparacao nao disponivel",
                        ha="center", va="center", color=text_sub, fontsize=14,
                        transform=ax.transAxes)
                ax.axis("off")

            if "final_score" in r:
                fig_pair.text(
                    0.5, 0.05,
                    f"Embedding: {r['emb_score']:.4f}   |   "
                    f"ORB: {r['orb_score']:.4f}   |   "
                    f"Score Final: {r['final_score']:.4f}",
                    ha="center", fontsize=11, color=accent,
                )

            pdf.savefig(fig_pair, facecolor=bg)
            plt.close(fig_pair)

    log.info("PDF executivo salvo em: %s", pdf_path)


# --- Pipeline principal ------------------------------------------------------

def run_pipeline(ref_dir: str, inspection_dir: str, report_dir: str = "reports") -> list[dict]:
    ref_path = Path(ref_dir)
    ins_path = Path(inspection_dir)

    if not ref_path.is_dir():
        raise FileNotFoundError(f"Diretorio de referencia nao encontrado: {ref_dir}")
    if not ins_path.is_dir():
        raise FileNotFoundError(f"Diretorio de inspecao nao encontrado: {inspection_dir}")

    pairs = _find_pairs(ref_path, ins_path)
    if not pairs:
        raise ValueError("Nenhum par encontrado. Verifique se os nomes dos arquivos coincidem.")

    report_path = Path(report_dir)
    comp_dir    = report_path / "comparisons"
    comp_dir.mkdir(parents=True, exist_ok=True)

    log.info("Iniciando analise de %d par(es)...", len(pairs))
    log.info("Backend de IA: %s", embedding.backend())

    results:  list[dict] = []
    ok_count: int        = 0

    for idx, (ref, ins) in enumerate(pairs, start=1):
        try:
            result = _analyze_pair(ref, ins, comp_dir)
            results.append(result)
            verdict = "OK" if result["status"] == "OK" else "DIFF"
            print(
                f"[{idx:>3}/{len(pairs)}] [{verdict}]  {ref.name:<40} "
                f"Final={result['final_score']:.4f}  {result['recommendation']}"
            )
            if result["status"] == "OK":
                ok_count += 1
        except Exception as exc:
            log.error("Falha ao processar %s: %s", ref.name, exc)
            results.append({"reference": str(ref), "inspection": str(ins),
                             "status": "ERRO", "error": str(exc)})

    total   = len(pairs)
    damaged = sum(1 for r in results if r.get("status") == "DIFERENCA")
    errors  = sum(1 for r in results if r.get("status") == "ERRO")

    print(f"\n{'='*60}")
    print(f"  RESUMO: {total} pares analisados")
    print(f"  Integros   : {ok_count}")
    print(f"  Diferencas : {damaged}")
    if errors:
        print(f"  Erros      : {errors}")
    print(f"{'='*60}\n")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "generated_at":   datetime.now().isoformat(),
        "reference_dir":  str(ref_path),
        "inspection_dir": str(ins_path),
        "ai_backend":     embedding.backend(),
        "summary":        {"total": total, "ok": ok_count, "damaged": damaged, "errors": errors},
        "results":        results,
    }

    json_file = report_path / f"report_{timestamp}.json"
    json_file.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    log.info("JSON salvo em: %s", json_file)

    pdf_file = report_path / f"report_{timestamp}.pdf"
    try:
        _generate_pdf(report, pdf_file)
    except Exception as exc:
        log.error("Falha ao gerar PDF: %s", exc)

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline de inspecao AeroInspect")
    parser.add_argument("--reference-dir",  default="data/reference",
                        help="Pasta com fotos ANTES. Padrao: data/reference")
    parser.add_argument("--inspection-dir", default="data/inspection",
                        help="Pasta com fotos DEPOIS. Padrao: data/inspection")
    parser.add_argument("--report-dir",     default="reports",
                        help="Pasta de saida dos relatorios. Padrao: reports/")
    args = parser.parse_args()

    try:
        run_pipeline(args.reference_dir, args.inspection_dir, args.report_dir)
    except (FileNotFoundError, ValueError) as exc:
        log.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
