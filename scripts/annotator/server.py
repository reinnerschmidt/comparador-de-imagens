#!/usr/bin/env python3
"""Servidor de anotação de imagens de aeronave.

Uso:
    python scripts/annotator/server.py
    Acesse: http://localhost:5050
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file, send_from_directory

# ─── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT  = Path(__file__).parent.parent.parent
SRC_DIR       = PROJECT_ROOT / "src"
STATIC_DIR    = Path(__file__).parent / "static"
BEFORE_DIR    = PROJECT_ROOT / "data" / "load" / "before"
AFTER_DIR     = PROJECT_ROOT / "data" / "load" / "after"
ANNOTATIONS   = PROJECT_ROOT / "data" / "labeled" / "annotations.json"
CONFIG_FILE   = PROJECT_ROOT / "src" / "config.py"

sys.path.insert(0, str(SRC_DIR))

app = Flask(__name__, static_folder=str(STATIC_DIR))

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _load_annotations() -> dict:
    if ANNOTATIONS.exists():
        return json.loads(ANNOTATIONS.read_text(encoding="utf-8"))
    return {}


def _save_annotations(data: dict) -> None:
    ANNOTATIONS.parent.mkdir(parents=True, exist_ok=True)
    ANNOTATIONS.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _find_pairs() -> list[dict]:
    """Retorna pares de imagens com mesmo nome em before/ e after/."""
    before = {f.name: f for f in BEFORE_DIR.iterdir() if f.suffix.lower() in IMAGE_EXTS}
    after  = {f.name: f for f in AFTER_DIR.iterdir()  if f.suffix.lower() in IMAGE_EXTS}
    common = sorted(set(before) & set(after))
    return [{"filename": name, "before": str(before[name]), "after": str(after[name])} for name in common]


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(STATIC_DIR), "index.html")


@app.route("/api/pairs")
def api_pairs():
    pairs       = _find_pairs()
    annotations = _load_annotations()
    for p in pairs:
        ann = annotations.get(p["filename"])
        p["annotated"] = ann is not None
        p["label"]     = ann["label"] if ann else None
    return jsonify(pairs)


@app.route("/image/before/<filename>")
def serve_before(filename: str):
    path = BEFORE_DIR / filename
    if not path.exists() or path.suffix.lower() not in IMAGE_EXTS:
        abort(404)
    return send_file(str(path))


@app.route("/image/after/<filename>")
def serve_after(filename: str):
    path = AFTER_DIR / filename
    if not path.exists() or path.suffix.lower() not in IMAGE_EXTS:
        abort(404)
    return send_file(str(path))


@app.route("/api/annotate", methods=["POST"])
def api_annotate():
    body     = request.get_json(force=True)
    filename = body.get("filename")
    label    = body.get("label")        # 0 = idênticas, 1 = dano
    circle   = body.get("circle")      # {x, y, radius} or null

    if not filename or label not in (0, 1):
        abort(400, "filename e label são obrigatórios")

    data = _load_annotations()
    data[filename] = {
        "label":        label,
        "circle":       circle,
        "annotated_at": datetime.now().isoformat(timespec="seconds"),
    }
    _save_annotations(data)
    return jsonify({"ok": True})


@app.route("/api/annotations")
def api_annotations():
    return jsonify(_load_annotations())


@app.route("/api/calibrate", methods=["POST"])
def api_calibrate():
    """Roda o pipeline Embedding+ORB nos pares anotados e retorna o threshold ideal."""
    try:
        import numpy as np
        from sklearn.metrics import average_precision_score, precision_recall_curve

        from fusion.decision import fuse_and_decide
        from preprocessing.image_loader import _load_with_cv2
        from similarity.embedding import compute_embedding_score
        from similarity.orb import compute_orb_score
    except ImportError as e:
        return jsonify({"error": f"Dependência não encontrada: {e}"}), 500

    annotations = _load_annotations()
    pairs       = _find_pairs()

    results = []
    for pair in pairs:
        ann = annotations.get(pair["filename"])
        if ann is None:
            continue  # pula não anotados

        try:
            img_ref = _load_with_cv2(pair["before"])
            img_cur = _load_with_cv2(pair["after"])
            emb_s   = compute_embedding_score(img_ref, img_cur)
            orb_s   = compute_orb_score(img_ref, img_cur)
            final_s, _ = fuse_and_decide(emb_s, orb_s)
            results.append({
                "filename":    pair["filename"],
                "label":       ann["label"],
                "embedding":   round(emb_s, 4),
                "orb":         round(orb_s, 4),
                "final_score": round(final_s, 4),
            })
        except Exception as exc:
            results.append({"filename": pair["filename"], "error": str(exc)})

    valid = [r for r in results if "error" not in r]
    if len(valid) < 2:
        return jsonify({
            "error": "Anote pelo menos 2 pares (com rótulos diferentes) para recalibrar.",
            "results": results,
        }), 422

    scores = np.array([r["final_score"] for r in valid])
    labels = np.array([r["label"]       for r in valid])

    # Score de anomalia: maior final_score = mais similar = menos dano
    anomaly = 1.0 - scores

    try:
        precision, recall, thresholds = precision_recall_curve(labels, anomaly)
        ap = float(average_precision_score(labels, anomaly))
        f1 = 2 * precision * recall / (precision + recall + 1e-8)

        # Melhor F1 com recall >= 0.80
        min_recall = 0.80
        valid_idx  = recall >= min_recall
        best_idx   = int(np.argmax(np.where(valid_idx, f1, 0.0))) if valid_idx.any() else int(np.argmax(f1))

        best_anomaly_t  = float(thresholds[best_idx]) if best_idx < len(thresholds) else float(thresholds[-1])
        best_decision_t = round(1.0 - best_anomaly_t, 3)

        return jsonify({
            "threshold":  best_decision_t,
            "precision":  round(float(precision[best_idx]), 3),
            "recall":     round(float(recall[best_idx]), 3),
            "f1":         round(float(f1[best_idx]), 3),
            "ap":         round(ap, 3),
            "n_pairs":    len(valid),
            "results":    results,
        })
    except Exception as exc:
        return jsonify({"error": str(exc), "results": results}), 500


@app.route("/api/save-threshold", methods=["POST"])
def api_save_threshold():
    """Atualiza DECISION_THRESHOLD em src/config.py."""
    body      = request.get_json(force=True)
    new_value = body.get("threshold")

    if new_value is None or not isinstance(new_value, (int, float)):
        abort(400, "threshold inválido")

    content = CONFIG_FILE.read_text(encoding="utf-8")
    updated = re.sub(
        r"(DECISION_THRESHOLD\s*:\s*float\s*=\s*)[0-9.]+",
        rf"\g<1>{new_value:.3f}",
        content,
    )

    if updated == content:
        return jsonify({"ok": False, "error": "DECISION_THRESHOLD não encontrado em config.py"}), 500

    CONFIG_FILE.write_text(updated, encoding="utf-8")
    return jsonify({"ok": True, "new_value": new_value})


@app.route("/api/current-threshold")
def api_current_threshold():
    content = CONFIG_FILE.read_text(encoding="utf-8")
    match   = re.search(r"DECISION_THRESHOLD\s*:\s*float\s*=\s*([0-9.]+)", content)
    value   = float(match.group(1)) if match else None
    return jsonify({"threshold": value})


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  🛩️  Anotador de Inspeção Aeronáutica")
    print("=" * 60)
    print(f"  Acesse: http://localhost:5050")
    print(f"  Pares:  {BEFORE_DIR}")
    print(f"  Dados:  {ANNOTATIONS}")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=5050, debug=False)
