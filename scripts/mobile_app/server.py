#!/usr/bin/env python3
"""AeroInspect Mobile — Backend Flask MVP Production.

Local:    python scripts/mobile_app/server.py   (SQLite automático)
Railway:  DATABASE_URL setado automaticamente → usa PostgreSQL
"""
from __future__ import annotations

import base64
import json
import os
import sqlite3
import sys
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

# ─── Paths ───────────────────────────────────────────────────────────────────

BASE_DIR   = Path(__file__).parent.parent.parent   # raiz do projeto
STATIC_DIR = Path(__file__).parent / "static"
DATA_DIR   = BASE_DIR / "data"
PHOTOS_DIR = DATA_DIR / "inspections"
REPORTS_DIR = DATA_DIR / "reports"
COMP_DIR   = DATA_DIR / "comparisons"

for d in [DATA_DIR, PHOTOS_DIR, REPORTS_DIR, COMP_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Pipeline IA (src/)
sys.path.insert(0, str(BASE_DIR / "src"))

DB_URL = os.environ.get("DATABASE_URL", "")

if DB_URL:
    import psycopg2
    import psycopg2.extras

app = Flask(__name__, static_folder=str(STATIC_DIR))
app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024  # 30 MB

# ─── DB abstraction ───────────────────────────────────────────────────────────

PH = "%s" if DB_URL else "?"


@contextmanager
def db_conn():
    if DB_URL:
        url = DB_URL.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(url)
        conn.autocommit = False
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DATA_DIR / "aero.db"))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def fetchall(conn, sql: str, params=()) -> list[dict]:
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    if DB_URL:
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in rows]
    return [dict(r) for r in rows]


def fetchone(conn, sql: str, params=()) -> dict | None:
    rows = fetchall(conn, sql, params)
    return rows[0] if rows else None


def execute_returning(conn, sql: str, params=()) -> int:
    cur = conn.cursor()
    if DB_URL:
        cur.execute(sql + " RETURNING id", params)
        return cur.fetchone()[0]
    cur.execute(sql, params)
    return cur.lastrowid


# ─── Schema ───────────────────────────────────────────────────────────────────

SCHEMA_SQLITE = """
    CREATE TABLE IF NOT EXISTS aircraft (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        serial  TEXT NOT NULL UNIQUE,
        name    TEXT NOT NULL,
        created TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS areas (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL UNIQUE,
        mask_points TEXT,
        mask_thumb  TEXT,
        ref_width   INTEGER,
        ref_height  INTEGER,
        created     TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS inspection_photos (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        aircraft_id INTEGER NOT NULL REFERENCES aircraft(id) ON DELETE CASCADE,
        area_id     INTEGER NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
        mode        TEXT NOT NULL CHECK(mode IN ('before','after')),
        file_path   TEXT NOT NULL,
        captured_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS analyses (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        aircraft_id     INTEGER NOT NULL REFERENCES aircraft(id) ON DELETE CASCADE,
        area_id         INTEGER NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
        before_photo_id INTEGER REFERENCES inspection_photos(id),
        after_photo_id  INTEGER REFERENCES inspection_photos(id),
        emb_score       REAL,
        orb_score       REAL,
        final_score     REAL,
        status          TEXT,
        heatmap_path    TEXT,
        pdf_path        TEXT,
        created_at      TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS feedback (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        analysis_id             INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
        classification_correct  INTEGER,
        damage_location_correct INTEGER,
        corrected_region        TEXT,
        notes                   TEXT,
        created_at              TEXT DEFAULT (datetime('now'))
    );
"""

SCHEMA_PG = """
    CREATE TABLE IF NOT EXISTS aircraft (
        id      SERIAL PRIMARY KEY,
        serial  TEXT NOT NULL UNIQUE,
        name    TEXT NOT NULL,
        created TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS areas (
        id          SERIAL PRIMARY KEY,
        name        TEXT NOT NULL UNIQUE,
        mask_points TEXT,
        mask_thumb  TEXT,
        ref_width   INTEGER,
        ref_height  INTEGER,
        created     TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS inspection_photos (
        id          SERIAL PRIMARY KEY,
        aircraft_id INTEGER NOT NULL REFERENCES aircraft(id) ON DELETE CASCADE,
        area_id     INTEGER NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
        mode        TEXT NOT NULL CHECK(mode IN ('before','after')),
        file_path   TEXT NOT NULL,
        captured_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS analyses (
        id              SERIAL PRIMARY KEY,
        aircraft_id     INTEGER NOT NULL REFERENCES aircraft(id) ON DELETE CASCADE,
        area_id         INTEGER NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
        before_photo_id INTEGER REFERENCES inspection_photos(id),
        after_photo_id  INTEGER REFERENCES inspection_photos(id),
        emb_score       REAL,
        orb_score       REAL,
        final_score     REAL,
        status          TEXT,
        heatmap_path    TEXT,
        pdf_path        TEXT,
        created_at      TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS feedback (
        id                      SERIAL PRIMARY KEY,
        analysis_id             INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
        classification_correct  BOOLEAN,
        damage_location_correct BOOLEAN,
        corrected_region        TEXT,
        notes                   TEXT,
        created_at              TIMESTAMPTZ DEFAULT NOW()
    );
"""


def init_db() -> None:
    with db_conn() as conn:
        cur = conn.cursor()
        # Migração legada: remove tabela areas com aircraft_id
        try:
            cur.execute("SELECT aircraft_id FROM areas LIMIT 1")
            cur.execute("DROP TABLE areas")
        except Exception:
            conn.rollback()  # reset aborted transaction before continuing

        schema = SCHEMA_PG if DB_URL else SCHEMA_SQLITE
        for stmt in schema.split(";"):
            stmt = stmt.strip()
            if stmt:
                cur.execute(stmt)



init_db()


# ─── Health check ─────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})


# ─── SPA ──────────────────────────────────────────────────────────────────────

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path: str):
    # Serve arquivos de fotos e relatórios
    if path.startswith("data/"):
        rel = path[len("data/"):]
        return send_from_directory(str(DATA_DIR), rel)
    if path and (STATIC_DIR / path).exists():
        return send_from_directory(str(STATIC_DIR), path)
    return send_from_directory(str(STATIC_DIR), "index.html")


# ─── Aircraft ─────────────────────────────────────────────────────────────────

@app.route("/api/aircraft")
def list_aircraft():
    with db_conn() as conn:
        rows = fetchall(conn, "SELECT id, serial, name, created FROM aircraft ORDER BY created DESC")
    return jsonify(rows)


@app.route("/api/aircraft", methods=["POST"])
def create_aircraft():
    data   = request.get_json(force=True)
    serial = (data.get("serial") or "").strip().upper()
    name   = (data.get("name")   or "").strip()
    if not serial or not name:
        return jsonify({"error": "serial e name são obrigatórios"}), 400
    try:
        with db_conn() as conn:
            new_id = execute_returning(
                conn,
                f"INSERT INTO aircraft (serial, name) VALUES ({PH}, {PH})",
                (serial, name),
            )
        return jsonify({"id": new_id, "serial": serial, "name": name}), 201
    except Exception as e:
        if "unique" in str(e).lower():
            return jsonify({"error": "Número de série já cadastrado"}), 409
        return jsonify({"error": str(e)}), 500


@app.route("/api/aircraft/<int:aid>", methods=["DELETE"])
def delete_aircraft(aid: int):
    with db_conn() as conn:
        conn.cursor().execute(f"DELETE FROM aircraft WHERE id = {PH}", (aid,))
    return jsonify({"ok": True})


# ─── Areas (Globais) ──────────────────────────────────────────────────────────

@app.route("/api/areas")
def list_areas():
    with db_conn() as conn:
        rows = fetchall(conn, "SELECT id, name, mask_thumb, created FROM areas ORDER BY name")
    return jsonify(rows)


@app.route("/api/areas", methods=["POST"])
def create_area():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name é obrigatório"}), 400
    try:
        with db_conn() as conn:
            new_id = execute_returning(
                conn, f"INSERT INTO areas (name) VALUES ({PH})", (name,)
            )
        return jsonify({"id": new_id, "name": name}), 201
    except Exception:
        return jsonify({"error": "Área já cadastrada"}), 409


@app.route("/api/areas/<int:area_id>", methods=["DELETE"])
def delete_area(area_id: int):
    with db_conn() as conn:
        conn.cursor().execute(f"DELETE FROM areas WHERE id = {PH}", (area_id,))
    return jsonify({"ok": True})


@app.route("/api/areas/<int:area_id>/mask")
def get_mask(area_id: int):
    try:
        with db_conn() as conn:
            row = fetchone(conn,
                f"SELECT name, mask_points, mask_thumb FROM areas WHERE id = {PH}",
                (area_id,))
        if not row:
            return jsonify({"error": f"Modelo #{area_id} não encontrado"}), 404
        return jsonify({
            "name":        row["name"],
            "mask_points": json.loads(row["mask_points"]) if row["mask_points"] else [],
            "mask_thumb":  row["mask_thumb"],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/areas/<int:area_id>/mask", methods=["PUT"])
def save_mask(area_id: int):
    data   = request.get_json(force=True)
    points = json.dumps(data.get("points", []))
    thumb  = data.get("thumbnail", "")
    ref_w  = data.get("ref_width")
    ref_h  = data.get("ref_height")
    with db_conn() as conn:
        conn.cursor().execute(
            f"UPDATE areas SET mask_points={PH}, mask_thumb={PH}, "
            f"ref_width={PH}, ref_height={PH} WHERE id={PH}",
            (points, thumb, ref_w, ref_h, area_id),
        )
    return jsonify({"ok": True})


# ─── Photos ───────────────────────────────────────────────────────────────────

@app.route("/api/photos/upload", methods=["POST"])
def upload_photo():
    """Recebe foto em base64, salva em disco e registra no banco."""
    data        = request.get_json(force=True)
    aircraft_id = data.get("aircraft_id")
    area_id     = data.get("area_id")
    mode        = (data.get("mode") or "").lower()
    image_b64   = data.get("image")  # data:image/jpeg;base64,...

    if not all([aircraft_id, area_id, mode, image_b64]):
        return jsonify({"error": "aircraft_id, area_id, mode e image são obrigatórios"}), 400
    if mode not in ("before", "after"):
        return jsonify({"error": "mode deve ser 'before' ou 'after'"}), 400

    # Decodifica imagem
    try:
        if "," in image_b64:
            image_b64 = image_b64.split(",", 1)[1]
        img_bytes = base64.b64decode(image_b64)
    except Exception:
        return jsonify({"error": "Imagem base64 inválida"}), 400

    # Busca serial da aeronave e nome da área
    with db_conn() as conn:
        aircraft = fetchone(conn, f"SELECT serial FROM aircraft WHERE id={PH}", (aircraft_id,))
        area     = fetchone(conn, f"SELECT name FROM areas WHERE id={PH}", (area_id,))

    if not aircraft or not area:
        return jsonify({"error": "Aeronave ou área não encontrada"}), 404

    # Salva arquivo
    ts       = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_{mode}.jpg"
    folder   = PHOTOS_DIR / aircraft["serial"] / area["name"]
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / filename
    file_path.write_bytes(img_bytes)

    rel_path = str(file_path.relative_to(BASE_DIR))

    with db_conn() as conn:
        photo_id = execute_returning(
            conn,
            f"INSERT INTO inspection_photos (aircraft_id, area_id, mode, file_path) "
            f"VALUES ({PH},{PH},{PH},{PH})",
            (aircraft_id, area_id, mode, rel_path),
        )

    return jsonify({"id": photo_id, "file_path": rel_path, "mode": mode}), 201


@app.route("/api/aircraft/<int:aircraft_id>/areas/<int:area_id>/photos")
def list_photos(aircraft_id: int, area_id: int):
    """Lista as fotos BEFORE e AFTER mais recentes da área neste avião."""
    with db_conn() as conn:
        rows = fetchall(
            conn,
            f"SELECT id, mode, file_path, captured_at FROM inspection_photos "
            f"WHERE aircraft_id={PH} AND area_id={PH} ORDER BY captured_at DESC",
            (aircraft_id, area_id),
        )
    # Converte path para URL acessível
    result = {"before": None, "after": None, "all": []}
    for r in rows:
        url = "/" + r["file_path"].replace("\\", "/")
        entry = {**r, "url": url}
        result["all"].append(entry)
        if r["mode"] == "before" and not result["before"]:
            result["before"] = entry
        if r["mode"] == "after" and not result["after"]:
            result["after"] = entry
    return jsonify(result)


# ─── Analysis ─────────────────────────────────────────────────────────────────

def _run_area_analysis(aircraft_id: int, area_id: int) -> dict:
    """Executa pipeline IA para um par BEFORE/AFTER. Retorna resultado."""
    from analyzer import analyze_pair

    with db_conn() as conn:
        before = fetchone(
            conn,
            f"SELECT id, file_path FROM inspection_photos "
            f"WHERE aircraft_id={PH} AND area_id={PH} AND mode='before' "
            f"ORDER BY captured_at DESC LIMIT 1",
            (aircraft_id, area_id),
        )
        after = fetchone(
            conn,
            f"SELECT id, file_path FROM inspection_photos "
            f"WHERE aircraft_id={PH} AND area_id={PH} AND mode='after' "
            f"ORDER BY captured_at DESC LIMIT 1",
            (aircraft_id, area_id),
        )

    if not before:
        raise ValueError("Foto BEFORE não encontrada para esta área")
    if not after:
        raise ValueError("Foto AFTER não encontrada para esta área")

    before_path = str(BASE_DIR / before["file_path"])
    after_path  = str(BASE_DIR / after["file_path"])

    result = analyze_pair(before_path, after_path, str(COMP_DIR))

    with db_conn() as conn:
        analysis_id = execute_returning(
            conn,
            f"INSERT INTO analyses (aircraft_id, area_id, before_photo_id, after_photo_id, "
            f"emb_score, orb_score, final_score, status, heatmap_path) "
            f"VALUES ({PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH})",
            (
                aircraft_id, area_id,
                before["id"], after["id"],
                result["emb_score"], result["orb_score"], result["final_score"],
                result["status"], result.get("heatmap_path"),
            ),
        )
    result["analysis_id"] = analysis_id

    # Convert absolute heatmap path to relative for URL serving
    heatmap_abs = result.get("heatmap_path")
    if heatmap_abs:
        try:
            result["heatmap_path"] = str(Path(heatmap_abs).relative_to(BASE_DIR))
        except ValueError:
            pass  # already relative or outside BASE_DIR

    return result


@app.route("/api/aircraft/<int:aircraft_id>/areas/<int:area_id>/analyze", methods=["POST"])
def analyze_area(aircraft_id: int, area_id: int):
    """Dispara análise IA para uma área específica."""
    try:
        result = _run_area_analysis(aircraft_id, area_id)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Falha na análise: {e}"}), 500


@app.route("/api/aircraft/<int:aircraft_id>/analyze", methods=["POST"])
def analyze_aircraft(aircraft_id: int):
    """Dispara análise IA para todas as áreas com BEFORE+AFTER do avião."""
    with db_conn() as conn:
        area_ids = fetchall(
            conn,
            f"SELECT DISTINCT area_id FROM inspection_photos WHERE aircraft_id={PH}",
            (aircraft_id,),
        )

    results = []
    for row in area_ids:
        aid = row["area_id"]
        try:
            r = _run_area_analysis(aircraft_id, aid)
            results.append({"area_id": aid, **r})
        except ValueError as e:
            results.append({"area_id": aid, "error": str(e)})
        except Exception as e:
            results.append({"area_id": aid, "error": f"Falha: {e}"})

    return jsonify({"results": results}), 200


@app.route("/api/analyses/<int:analysis_id>")
def get_analysis(analysis_id: int):
    with db_conn() as conn:
        row = fetchone(conn,
            f"SELECT * FROM analyses WHERE id={PH}", (analysis_id,))
    if not row:
        return jsonify({"error": "Análise não encontrada"}), 404
    if row.get("heatmap_path"):
        row["heatmap_url"] = "/" + row["heatmap_path"].replace("\\", "/")
    return jsonify(row)


@app.route("/api/aircraft/<int:aircraft_id>/areas/<int:area_id>/analyses")
def list_area_analyses(aircraft_id: int, area_id: int):
    """Lista análises desta área, mais recente primeiro."""
    with db_conn() as conn:
        rows = fetchall(
            conn,
            f"SELECT id, final_score, status, heatmap_path, created_at "
            f"FROM analyses WHERE aircraft_id={PH} AND area_id={PH} "
            f"ORDER BY created_at DESC",
            (aircraft_id, area_id),
        )
    for r in rows:
        if r.get("heatmap_path"):
            r["heatmap_url"] = "/" + r["heatmap_path"].replace("\\", "/")
    return jsonify(rows)


# ─── PDF Report ───────────────────────────────────────────────────────────────

@app.route("/api/aircraft/<int:aircraft_id>/report")
def aircraft_report(aircraft_id: int):
    """Gera e serve o relatório PDF executivo do avião."""
    try:
        from fpdf import FPDF
    except ImportError:
        return jsonify({"error": "fpdf2 não instalado — adicione fpdf2 ao requirements.txt"}), 500

    try:
        with db_conn() as conn:
            aircraft = fetchone(conn, f"SELECT * FROM aircraft WHERE id={PH}", (aircraft_id,))
            analyses = fetchall(
                conn,
                f"SELECT a.*, ar.name as area_name FROM analyses a "
                f"JOIN areas ar ON ar.id = a.area_id "
                f"WHERE a.aircraft_id={PH} ORDER BY a.created_at DESC",
                (aircraft_id,),
            )

        if not aircraft:
            return jsonify({"error": "Aeronave não encontrada"}), 404
        if not analyses:
            return jsonify({"error": "Sem análises para gerar relatório"}), 404

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # ── Cabeçalho ──
        pdf.set_font("Helvetica", "B", 20)
        pdf.set_text_color(26, 86, 219)   # azul Embraer
        pdf.cell(0, 12, "EMBRAER — AeroInspect", ln=True, align="C")
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(60, 60, 60)
        pdf.cell(0, 8, f"Relatório de Inspeção — Aeronave: {aircraft['serial']} ({aircraft['name']})", ln=True, align="C")
        pdf.cell(0, 6, f"Gerado em: {datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC", ln=True, align="C")
        pdf.ln(6)

        # ── Resumo ──
        total    = len(analyses)
        damaged  = sum(1 for a in analyses if a["status"] != "OK")
        ok_count = total - damaged
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(0, 9, "Resumo Executivo", ln=True)
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(60, 7, f"Total de áreas: {total}")
        pdf.set_text_color(16, 120, 50)
        pdf.cell(60, 7, f"Íntegras: {ok_count}")
        pdf.set_text_color(200, 30, 30)
        pdf.cell(60, 7, f"Com diferença: {damaged}", ln=True)
        pdf.set_text_color(30, 30, 30)
        pdf.ln(4)

        # ── Tabela de resultados ──
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_fill_color(26, 86, 219)
        pdf.set_text_color(255, 255, 255)
        col_w = [55, 22, 22, 22, 60]
        headers = ["Área", "Semântico", "ORB", "Final", "Status"]
        for i, h in enumerate(headers):
            pdf.cell(col_w[i], 8, h, border=1, fill=True, align="C")
        pdf.ln()

        pdf.set_font("Helvetica", "", 10)
        for a in analyses:
            status = a["status"] or "—"
            ok = status == "OK"
            pdf.set_text_color(16, 100, 40) if ok else pdf.set_text_color(180, 20, 20)
            row = [
                (a.get("area_name") or "")[:30],
                f"{a['emb_score']:.3f}",
                f"{a['orb_score']:.3f}",
                f"{a['final_score']:.3f}",
                "Íntegro" if ok else "⚠ Diferença detectada",
            ]
            for i, cell in enumerate(row):
                pdf.cell(col_w[i], 7, cell, border=1, align="C" if i > 0 else "L")
            pdf.ln()
            pdf.set_text_color(30, 30, 30)

        pdf.ln(8)
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(0, 6, "Este relatório foi gerado automaticamente pelo sistema AeroInspect e deve ser validado por inspetor certificado.", ln=True)

        ts       = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        pdf_name = f"report_{aircraft['serial']}_{ts}.pdf"
        pdf_path = REPORTS_DIR / pdf_name
        pdf.output(str(pdf_path))

        return send_from_directory(
            str(REPORTS_DIR), pdf_name,
            as_attachment=True,
            download_name=f"AeroInspect_{aircraft['serial']}.pdf",
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Feedback ─────────────────────────────────────────────────────────────────

@app.route("/api/feedback", methods=["POST"])
def save_feedback():
    data        = request.get_json(force=True)
    analysis_id = data.get("analysis_id")
    if not analysis_id:
        return jsonify({"error": "analysis_id é obrigatório"}), 400

    class_ok    = data.get("classification_correct")
    location_ok = data.get("damage_location_correct")
    region      = json.dumps(data.get("corrected_region")) if data.get("corrected_region") else None
    notes       = data.get("notes", "")

    with db_conn() as conn:
        fb_id = execute_returning(
            conn,
            f"INSERT INTO feedback (analysis_id, classification_correct, "
            f"damage_location_correct, corrected_region, notes) "
            f"VALUES ({PH},{PH},{PH},{PH},{PH})",
            (analysis_id, class_ok, location_ok, region, notes),
        )
    return jsonify({"id": fb_id, "ok": True}), 201


@app.route("/api/feedback/<int:analysis_id>")
def list_feedback(analysis_id: int):
    with db_conn() as conn:
        rows = fetchall(
            conn,
            f"SELECT * FROM feedback WHERE analysis_id={PH} ORDER BY created_at DESC",
            (analysis_id,),
        )
    return jsonify(rows)


# ─── Entry ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5051))
    print(f"\n🛩️  AeroInspect → http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
