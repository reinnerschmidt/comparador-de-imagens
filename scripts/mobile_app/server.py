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

import google.generativeai as genai
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
IS_POSTGRES = bool(DB_URL)

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
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
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
        name    TEXT,
        status  TEXT DEFAULT 'Ativo',
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
        position    TEXT,
        phase       TEXT DEFAULT 'Recebimento',
        mode        TEXT NOT NULL CHECK(mode IN ('before','after')),
        file_path   TEXT NOT NULL,
        captured_at TEXT DEFAULT (datetime('now')),
        has_manual_damage INTEGER DEFAULT 0,
        has_damage_check INTEGER DEFAULT 0, -- 0=Pendente, 1=Sem Dano, 2=Com Dano
        manual_damage_regions TEXT
    );
    CREATE TABLE IF NOT EXISTS analyses (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        aircraft_id     INTEGER NOT NULL REFERENCES aircraft(id) ON DELETE CASCADE,
        area_id         INTEGER NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
        position        TEXT,
        phase           TEXT DEFAULT 'Recebimento',
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
    CREATE TABLE IF NOT EXISTS global_areas (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL UNIQUE,
        created_at  TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS global_area_subareas (
        global_area_id INTEGER NOT NULL REFERENCES global_areas(id) ON DELETE CASCADE,
        subarea_id     INTEGER NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
        PRIMARY KEY (global_area_id, subarea_id)
    );
    CREATE TABLE IF NOT EXISTS position_areas (
        aircraft_id    INTEGER NOT NULL REFERENCES aircraft(id) ON DELETE CASCADE,
        position       TEXT NOT NULL,
        global_area_id INTEGER NOT NULL REFERENCES global_areas(id) ON DELETE CASCADE,
        PRIMARY KEY (aircraft_id, position, global_area_id)
    );
"""

SCHEMA_PG = """
    CREATE TABLE IF NOT EXISTS aircraft (
        id      SERIAL PRIMARY KEY,
        serial  TEXT NOT NULL UNIQUE,
        name    TEXT,
        status  TEXT DEFAULT 'Ativo',
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
        position    TEXT,
        phase       TEXT DEFAULT 'Recebimento',
        mode        TEXT NOT NULL CHECK(mode IN ('before','after')),
        file_path   TEXT NOT NULL,
        captured_at TIMESTAMPTZ DEFAULT NOW(),
        has_manual_damage BOOLEAN DEFAULT FALSE,
        has_damage_check INTEGER DEFAULT 0, -- 0=Pendente, 1=Sem Dano, 2=Com Dano
        manual_damage_regions TEXT
    );
    CREATE TABLE IF NOT EXISTS analyses (
        id              SERIAL PRIMARY KEY,
        aircraft_id     INTEGER NOT NULL REFERENCES aircraft(id) ON DELETE CASCADE,
        area_id         INTEGER NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
        position        TEXT,
        phase           TEXT DEFAULT 'Recebimento',
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
    CREATE TABLE IF NOT EXISTS global_areas (
        id          SERIAL PRIMARY KEY,
        name        TEXT NOT NULL UNIQUE,
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS global_area_subareas (
        global_area_id INTEGER NOT NULL REFERENCES global_areas(id) ON DELETE CASCADE,
        subarea_id     INTEGER NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
        PRIMARY KEY (global_area_id, subarea_id)
    );
    CREATE TABLE IF NOT EXISTS position_areas (
        aircraft_id    INTEGER NOT NULL REFERENCES aircraft(id) ON DELETE CASCADE,
        position       TEXT NOT NULL,
        global_area_id INTEGER NOT NULL REFERENCES global_areas(id) ON DELETE CASCADE,
        PRIMARY KEY (aircraft_id, position, global_area_id)
    );
"""


def init_db() -> None:
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(SCHEMA_SQLITE if not DB_URL else SCHEMA_PG)
        
        # Migração: Adicionar has_damage_check se não existir
        try:
            if not DB_URL:
                cur.execute("ALTER TABLE inspection_photos ADD COLUMN has_damage_check INTEGER DEFAULT 0")
            else:
                cur.execute("ALTER TABLE inspection_photos ADD COLUMN IF NOT EXISTS has_damage_check INTEGER DEFAULT 0")
        except:
            pass # Já existe
            
        # Migração: Adicionar status à aeronave
        try:
            if not DB_URL:
                cur.execute("ALTER TABLE aircraft ADD COLUMN status TEXT DEFAULT 'Ativo'")
            else:
                cur.execute("ALTER TABLE aircraft ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'Ativo'")
        except:
            pass
        
        conn.commit()
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

        # Migração: adiciona coluna position e phase se não existir (bancos anteriores)
        for table in ("inspection_photos", "analyses"):
            # Check if column exists first (safer for Postgres)
            try:
                cur.execute(f"SELECT position FROM {table} LIMIT 1")
            except Exception:
                conn.rollback()
                try:
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN position TEXT")
                except Exception:
                    conn.rollback()
            
            try:
                cur.execute(f"SELECT phase FROM {table} LIMIT 1")
            except Exception:
                conn.rollback()
                try:
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN phase TEXT DEFAULT 'Recebimento'")
                except Exception:
                    conn.rollback()
                    
        # Migração: colunas de dano manual
        try:
            cur.execute("SELECT has_manual_damage FROM inspection_photos LIMIT 1")
        except Exception:
            conn.rollback()
            try:
                col_type = "BOOLEAN DEFAULT FALSE" if DB_URL else "INTEGER DEFAULT 0"
                cur.execute(f"ALTER TABLE inspection_photos ADD COLUMN has_manual_damage {col_type}")
                cur.execute(f"ALTER TABLE inspection_photos ADD COLUMN manual_damage_regions TEXT")
            except Exception:
                conn.rollback()

        # Migração: coluna source (normal | kotsu)
        try:
            cur.execute("SELECT source FROM inspection_photos LIMIT 1")
        except Exception:
            conn.rollback()
            try:
                cur.execute("ALTER TABLE inspection_photos ADD COLUMN source TEXT DEFAULT 'normal'")
            except Exception:
                conn.rollback()


# ─── Heatmap URL helper ───────────────────────────────────────────────────────

def _heatmap_url(heatmap_path: str | None) -> str | None:
    """Normaliza path absoluto ou relativo para URL servível."""
    if not heatmap_path:
        return None
    from pathlib import Path as _P
    p = _P(heatmap_path)
    if p.is_absolute():
        try:
            heatmap_path = str(p.relative_to(BASE_DIR))
        except ValueError:
            return None
    return "/" + heatmap_path.replace("\\", "/")


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
        aircraft = fetchall(conn, "SELECT id, serial, name, status, created FROM aircraft ORDER BY created DESC")
        
        # Adicionar estatísticas para cada aeronave
        for ac in aircraft:
            aid = ac["id"]
            
            # Áreas inspecionadas (total único de sub-áreas com foto)
            inspected = fetchone(conn, 
                f"SELECT COUNT(DISTINCT area_id) as count FROM inspection_photos WHERE aircraft_id = {PH}", (aid,))
            ac["inspected_areas"] = inspected["count"] if inspected else 0
            
            # Total de danos únicos (IA ou Manual)
            damages = fetchone(conn,
                f"SELECT COUNT(DISTINCT area_id) as count FROM ("
                f"  SELECT area_id FROM analyses WHERE aircraft_id = {PH} AND status = 'Dano Detectado' "
                f"  UNION "
                f"  SELECT area_id FROM inspection_photos WHERE aircraft_id = {PH} AND has_damage_check = 2"
                f") as t", (aid, aid))
            
            ac["total_damages"] = damages["count"] if damages else 0
            ac["has_alert"] = ac["total_damages"] > 0
            
    return jsonify(aircraft)


@app.route("/api/aircraft/<int:aid>/stats")
def aircraft_stats(aid: int):
    """Retorna estatísticas detalhadas por posição para uma aeronave."""
    with db_conn() as conn:
        # Posições fixas (poderia vir de uma constante compartilhada)
        positions = ['P4', 'P3', 'P2', 'P1', 'P0', 'F30']
        stats = {}
        
        for pos in positions:
            # Áreas inspecionadas na posição
            inspected = fetchone(conn,
                f"SELECT COUNT(DISTINCT area_id) as count FROM inspection_photos WHERE aircraft_id = {PH} AND position = {PH}", 
                (aid, pos))
            
            # Total de danos únicos na posição (IA, Manual ou Kotsu)
            damages = fetchone(conn,
                f"SELECT COUNT(DISTINCT area_id) as count FROM ("
                f"  SELECT area_id FROM analyses WHERE aircraft_id = {PH} AND position = {PH} AND status = 'Dano Detectado' "
                f"  UNION "
                f"  SELECT area_id FROM inspection_photos WHERE aircraft_id = {PH} AND position = {PH} AND has_damage_check = 2"
                f") as t", (aid, pos, aid, pos))
            
            total_damages = damages["count"] if damages else 0
            
            stats[pos] = {
                "inspected_areas": inspected["count"] or 0,
                "total_damages": total_damages,
                "has_alert": total_damages > 0
            }
            
    return jsonify(stats)


@app.route("/api/aircraft", methods=["POST"])
def create_aircraft():
    data   = request.get_json(force=True)
    serial = (data.get("serial") or "").strip().upper()
    status = data.get("status", "Ativo")
    if not serial:
        return jsonify({"error": "Número de série é obrigatório"}), 400
    try:
        with db_conn() as conn:
            new_id = execute_returning(
                conn,
                f"INSERT INTO aircraft (serial, name, status) VALUES ({PH}, {PH}, {PH})",
                (serial, serial, status),  # name = serial por padrão
            )
        return jsonify({"id": new_id, "serial": serial, "name": serial, "status": status}), 201
    except Exception as e:
        if "unique" in str(e).lower():
            return jsonify({"error": "Número de série já cadastrado"}), 409
        return jsonify({"error": str(e)}), 500


@app.route("/api/aircraft/<int:aid>", methods=["DELETE"])
def delete_aircraft(aid: int):
    with db_conn() as conn:
        conn.cursor().execute(f"DELETE FROM aircraft WHERE id = {PH}", (aid,))
    return jsonify({"ok": True})


@app.route("/api/aircraft/<int:aid>/status", methods=["POST"])
def update_aircraft_status(aid: int):
    data = request.json
    status = data.get("status")
    with db_conn() as conn:
        conn.cursor().execute(f"UPDATE aircraft SET status = {PH} WHERE id = {PH}", (status, aid))
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


# ─── Global Areas (Pastas de Organização) ────────────────────────────────────

@app.route("/api/global_areas")
def list_global_areas():
    with db_conn() as conn:
        areas = fetchall(conn, "SELECT id, name, created_at FROM global_areas ORDER BY name")
    return jsonify(areas)

@app.route("/api/global_areas", methods=["POST"])
def create_global_area():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name: return jsonify({"error": "Nome obrigatório"}), 400
    with db_conn() as conn:
        new_id = execute_returning(conn, f"INSERT INTO global_areas (name) VALUES ({PH})", (name,))
    return jsonify({"id": new_id, "name": name}), 201

@app.route("/api/global_areas/<int:ga_id>", methods=["DELETE"])
def delete_global_area(ga_id: int):
    with db_conn() as conn:
        conn.cursor().execute(f"DELETE FROM global_areas WHERE id={PH}", (ga_id,))
    return jsonify({"ok": True})

@app.route("/api/global_areas/<int:ga_id>/subareas")
def list_global_area_subareas(ga_id: int):
    with db_conn() as conn:
        subs = fetchall(
            conn,
            f"SELECT a.id, a.name, a.mask_thumb FROM areas a "
            f"JOIN global_area_subareas gas ON gas.subarea_id = a.id "
            f"WHERE gas.global_area_id={PH} ORDER BY a.name",
            (ga_id,)
        )
    return jsonify(subs)

@app.route("/api/global_areas/<int:ga_id>/subareas", methods=["POST"])
def add_subarea_to_global_area(ga_id: int):
    data = request.get_json(force=True)
    area_id = data.get("area_id")
    if not area_id: return jsonify({"error": "area_id obrigatório"}), 400
    try:
        with db_conn() as conn:
            conn.cursor().execute(f"INSERT INTO global_area_subareas (global_area_id, subarea_id) VALUES ({PH}, {PH})", (ga_id, area_id))
        return jsonify({"ok": True}), 201
    except Exception:
        return jsonify({"error": "Já vinculado ou erro"}), 400

@app.route("/api/global_areas/<int:ga_id>/subareas/<int:area_id>", methods=["DELETE"])
def remove_subarea_from_global_area(ga_id: int, area_id: int):
    with db_conn() as conn:
        conn.cursor().execute(f"DELETE FROM global_area_subareas WHERE global_area_id={PH} AND subarea_id={PH}", (ga_id, area_id))
    return jsonify({"ok": True})

# ─── Aircraft/Position Areas (Ativação de pastas no avião) ───────────────────

@app.route("/api/aircraft/<int:aircraft_id>/pos/<position>/areas")
def list_position_areas(aircraft_id: int, position: str):
    position = position.upper()
    phase = request.args.get("phase")
    with db_conn() as conn:
        if phase:
            # Retorna as sub-áreas que possuem fotos e se possuem dano marcado
            rows = fetchall(
                conn,
                f"SELECT area_id, MAX(has_damage_check) as has_damage FROM inspection_photos "
                f"WHERE aircraft_id={PH} AND position={PH} AND phase={PH} GROUP BY area_id",
                (aircraft_id, position, phase),
            )
            return jsonify(rows)

        # Busca as áreas globais ativadas para este avião/pos
        groups = fetchall(
            conn,
            f"SELECT ga.id, ga.name FROM global_areas ga "
            f"JOIN position_areas pa ON pa.global_area_id = ga.id "
            f"WHERE pa.aircraft_id={PH} AND pa.position={PH} ORDER BY ga.name",
            (aircraft_id, position)
        )
        for g in groups:
            # Para cada área global, traz as subáreas que pertencem a ela
            g["subareas"] = fetchall(
                conn,
                f"SELECT a.id, a.name, a.mask_thumb FROM areas a "
                f"JOIN global_area_subareas gas ON gas.subarea_id = a.id "
                f"WHERE gas.global_area_id={PH} ORDER BY a.name",
                (g["id"],)
            )
    return jsonify(groups)

@app.route("/api/aircraft/<int:aircraft_id>/pos/<position>/areas", methods=["POST"])
def activate_position_area(aircraft_id: int, position: str):
    data = request.get_json(force=True)
    ga_id = data.get("global_area_id")
    if not ga_id: return jsonify({"error": "global_area_id obrigatório"}), 400
    position = position.upper()
    try:
        with db_conn() as conn:
            conn.cursor().execute(
                f"INSERT INTO position_areas (aircraft_id, position, global_area_id) VALUES ({PH}, {PH}, {PH})",
                (aircraft_id, position, ga_id)
            )
        return jsonify({"ok": True}), 201
    except Exception:
        return jsonify({"error": "Já ativa ou erro"}), 400

@app.route("/api/aircraft/<int:aircraft_id>/pos/<position>/areas/<int:ga_id>", methods=["DELETE"])
def deactivate_position_area(aircraft_id: int, position: str, ga_id: int):
    position = position.upper()
    with db_conn() as conn:
        conn.cursor().execute(
            f"DELETE FROM position_areas WHERE aircraft_id={PH} AND position={PH} AND global_area_id={PH}",
            (aircraft_id, position, ga_id)
        )
    return jsonify({"ok": True})


# ─── Photos ───────────────────────────────────────────────────────────────────

@app.route("/api/photos/<int:photo_id>", methods=["DELETE"])
def delete_photo(photo_id: int):
    with db_conn() as conn:
        photo = fetchone(conn, f"SELECT file_path FROM inspection_photos WHERE id={PH}", (photo_id,))
        if not photo:
            return jsonify({"error": "Foto não encontrada"}), 404
        
        # Deleta do banco
        conn.cursor().execute(f"DELETE FROM inspection_photos WHERE id={PH}", (photo_id,))
        
        # Tenta deletar o arquivo físico
        try:
            full_path = BASE_DIR / photo["file_path"]
            if full_path.exists():
                full_path.unlink()
        except Exception as e:
            print(f"Erro ao deletar arquivo: {e}")
            
    return jsonify({"ok": True})


@app.route("/api/photos/<int:photo_id>/check", methods=["POST"])
def update_photo_check(photo_id: int):
    data = request.get_json(force=True)
    status = data.get("status") # 1 ou 2
    if status not in [1, 2]:
        return jsonify({"error": "Status inválido"}), 400
    
    with db_conn() as conn:
        conn.cursor().execute(
            f"UPDATE inspection_photos SET has_damage_check={PH} WHERE id={PH}",
            (status, photo_id)
        )
    return jsonify({"ok": True})



# ─── Kotsu ────────────────────────────────────────────────────────────────────

@app.route("/api/kotsu", methods=["POST"])
def register_kotsu():
    """Registra um dano Kotsu com foto e regiões marcadas obrigatórias."""
    data = request.get_json(force=True)
    aircraft_id = data.get("aircraft_id")
    area_id     = data.get("area_id")
    position    = data.get("position")
    img_b64     = data.get("image")
    regions     = data.get("damage_regions")

    if not all([aircraft_id, area_id, img_b64]):
        return jsonify({"error": "aircraft_id, area_id e image são obrigatórios"}), 400
    if not regions or len(regions) == 0:
        return jsonify({"error": "É obrigatório marcar ao menos uma região de dano"}), 400

    # Busca serial e nome da área para organizar pastas
    with db_conn() as conn:
        aircraft = fetchone(conn, f"SELECT serial FROM aircraft WHERE id={PH}", (aircraft_id,))
        area     = fetchone(conn, f"SELECT name FROM areas WHERE id={PH}", (area_id,))
    
    if not aircraft or not area:
        return jsonify({"error": "Aeronave ou área não encontrada"}), 404

    # Salva imagem
    try:
        if "," in img_b64:
            img_b64 = img_b64.split(",", 1)[1]
        img_bytes = base64.b64decode(img_b64)
    except Exception:
        return jsonify({"error": "Imagem base64 inválida"}), 400

    ts       = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_kotsu.jpg"
    sub      = f"{position}/" if position else ""
    folder   = PHOTOS_DIR / aircraft["serial"] / sub / area["name"]
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / filename
    file_path.write_bytes(img_bytes)

    rel_path = str(file_path.relative_to(BASE_DIR))

    with db_conn() as conn:
        photo_id = execute_returning(
            conn,
            f"INSERT INTO inspection_photos (aircraft_id, area_id, position, phase, mode, file_path, "
            f"has_manual_damage, has_damage_check, manual_damage_regions, source) "
            f"VALUES ({PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH})",
            (aircraft_id, area_id, position or None, "Kotsu", "before",
             rel_path, True, 2, json.dumps(regions), "kotsu"),
        )

    return jsonify({"id": photo_id, "ok": True}), 201


@app.route("/api/kotsu/<int:aircraft_id>")
def list_kotsu(aircraft_id: int):
    """Lista registros Kotsu de um avião, opcionalmente filtrados por posição/área."""
    position = request.args.get("position")
    area_id  = request.args.get("area_id")

    with db_conn() as conn:
        if position and area_id:
            rows = fetchall(conn,
                f"SELECT id, area_id, position, file_path, captured_at, manual_damage_regions "
                f"FROM inspection_photos WHERE aircraft_id={PH} AND source='kotsu' AND position={PH} AND area_id={PH} "
                f"ORDER BY captured_at DESC",
                (aircraft_id, position.upper(), area_id))
        elif position:
            rows = fetchall(conn,
                f"SELECT id, area_id, position, file_path, captured_at, manual_damage_regions "
                f"FROM inspection_photos WHERE aircraft_id={PH} AND source='kotsu' AND position={PH} "
                f"ORDER BY captured_at DESC",
                (aircraft_id, position.upper()))
        else:
            rows = fetchall(conn,
                f"SELECT id, area_id, position, file_path, captured_at, manual_damage_regions "
                f"FROM inspection_photos WHERE aircraft_id={PH} AND source='kotsu' "
                f"ORDER BY captured_at DESC",
                (aircraft_id,))

    result = []
    for r in rows:
        regs = []
        try:
            if r.get("manual_damage_regions"):
                regs = json.loads(r["manual_damage_regions"])
        except:
            pass
        result.append({**r, "url": "/" + r["file_path"].replace("\\", "/"), "manual_damage_regions": regs})

    return jsonify(result)


@app.route("/api/photos/upload", methods=["POST"])

def upload_photo():
    """Recebe foto em base64, salva em disco e registra no banco."""
    data        = request.get_json(force=True)
    aircraft_id = data.get("aircraft_id")
    area_id     = data.get("area_id")
    mode        = (data.get("mode") or "").lower()
    image_b64   = data.get("image")  # data:image/jpeg;base64,...
    has_damage  = bool(data.get("has_manual_damage"))
    damage_regs = json.dumps(data.get("damage_regions", []))

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
    position = (data.get("position") or "").strip().upper() or None
    ts       = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_{mode}.jpg"
    sub      = f"{position}/" if position else ""
    folder   = PHOTOS_DIR / aircraft["serial"] / sub / area["name"]
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / filename
    file_path.write_bytes(img_bytes)

    rel_path = str(file_path.relative_to(BASE_DIR))

    phase = (data.get("phase") or "Recebimento").strip()
    
    # Determina o status inicial: se marcou dano manual, já entra como 'Com Dano' (2)
    has_damage_check = 2 if has_damage else 0
    
    with db_conn() as conn:
        photo_id = execute_returning(
            conn,
            f"INSERT INTO inspection_photos (aircraft_id, area_id, position, phase, mode, file_path, has_manual_damage, has_damage_check, manual_damage_regions) "
            f"VALUES ({PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH})",
            (aircraft_id, area_id, position, phase, mode, rel_path, has_damage, has_damage_check, damage_regs),
        )

    return jsonify({"id": photo_id, "file_path": rel_path, "mode": mode}), 201

@app.route("/api/aircraft/<int:aircraft_id>/areas/<int:area_id>/photos")
def list_photos(aircraft_id: int, area_id: int):
    """Lista as fotos BEFORE e AFTER mais recentes da área neste avião, filtradas por posição e fase."""
    position = request.args.get("position") or None
    phase = request.args.get("phase") or "Recebimento"
    
    with db_conn() as conn:
        if position:
            rows = fetchall(
                conn,
                f"SELECT id, mode, file_path, captured_at, has_manual_damage, has_damage_check, manual_damage_regions FROM inspection_photos "
                f"WHERE aircraft_id={PH} AND area_id={PH} AND position={PH} AND phase={PH} ORDER BY captured_at DESC",
                (aircraft_id, area_id, position.upper(), phase),
            )
        else:
            rows = fetchall(
                conn,
                f"SELECT id, mode, file_path, captured_at, has_manual_damage, has_damage_check, manual_damage_regions FROM inspection_photos "
                f"WHERE aircraft_id={PH} AND area_id={PH} AND position IS NULL AND phase={PH} ORDER BY captured_at DESC",
                (aircraft_id, area_id, phase),
            )
    result = {"before": None, "after": None, "all": []}
    for r in rows:
        url = "/" + r["file_path"].replace("\\", "/")
        # Converte manual_damage_regions de string para JSON
        regs = []
        try:
            if r.get("manual_damage_regions"):
                regs = json.loads(r["manual_damage_regions"])
        except:
            pass
            
        entry = {**r, "url": url, "manual_damage_regions": regs}
        result["all"].append(entry)
        if r["mode"] == "before" and not result["before"]:
            result["before"] = entry
        if r["mode"] == "after" and not result["after"]:
            result["after"] = entry
    return jsonify(result)




# ─── Analysis ─────────────────────────────────────────────────────────────────

def _run_area_analysis(aircraft_id: int, area_id: int, position: str | None = None, phase: str = "Recebimento") -> dict:
    """Executa pipeline IA para um par BEFORE/AFTER. Retorna resultado."""
    from analyzer import analyze_pair

    with db_conn() as conn:
        if position:
            pos_filter = f" AND position={PH}"
            pos_params = (aircraft_id, area_id, position.upper())
        else:
            pos_filter = ""
            pos_params = (aircraft_id, area_id)

        before = fetchone(
            conn,
            f"SELECT id, file_path, has_manual_damage, manual_damage_regions FROM inspection_photos "
            f"WHERE aircraft_id={PH} AND area_id={PH} AND mode='before' AND phase={PH}{pos_filter} "
            f"ORDER BY captured_at DESC LIMIT 1",
            (aircraft_id, area_id, phase, position.upper()) if position else (aircraft_id, area_id, phase),
        )
        after = fetchone(
            conn,
            f"SELECT id, file_path, has_manual_damage, manual_damage_regions FROM inspection_photos "
            f"WHERE aircraft_id={PH} AND area_id={PH} AND mode='after' AND phase={PH}{pos_filter} "
            f"ORDER BY captured_at DESC LIMIT 1",
            (aircraft_id, area_id, phase, position.upper()) if position else (aircraft_id, area_id, phase),
        )

    if not before:
        raise ValueError("Foto BEFORE não encontrada para esta área")
    if not after:
        raise ValueError("Foto AFTER não encontrada para esta área")

    before_path = str(BASE_DIR / before["file_path"])
    after_path  = str(BASE_DIR / after["file_path"])

    result = analyze_pair(before_path, after_path, str(COMP_DIR))
    
    # Integramos a marcação manual com a IA
    b_md = before.get("has_manual_damage")
    a_md = after.get("has_manual_damage")
    has_manual_damage = bool(b_md) or bool(a_md)
    
    ai_status = result["status"]
    is_false_negative = False
    
    if has_manual_damage:
        if ai_status == "OK":
            is_false_negative = True
        result["status"] = "Diferença Detectada"

    # Store relative heatmap path
    heatmap_abs = result.get("heatmap_path")
    rel_heatmap = None
    if heatmap_abs:
        try:
            rel_heatmap = str(Path(heatmap_abs).relative_to(BASE_DIR))
        except ValueError:
            rel_heatmap = heatmap_abs

    with db_conn() as conn:
        analysis_id = execute_returning(
            conn,
            f"INSERT INTO analyses (aircraft_id, area_id, position, phase, before_photo_id, after_photo_id, "
            f"emb_score, orb_score, final_score, status, heatmap_path) "
            f"VALUES ({PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH})",
            (
                aircraft_id, area_id, position, phase,
                before["id"], after["id"],
                result["emb_score"], result["orb_score"], result["final_score"],
                result["status"], rel_heatmap,
            ),
        )
        
        # Gera feedback automático para retreino se houver dano manual
        if has_manual_damage:
            regions = before.get("manual_damage_regions") if b_md else after.get("manual_damage_regions")
            execute_returning(
                conn,
                f"INSERT INTO feedback (analysis_id, classification_correct, damage_location_correct, corrected_region, notes) "
                f"VALUES ({PH},{PH},{PH},{PH},{PH})",
                (
                    analysis_id,
                    0 if is_false_negative else 1,
                    0,
                    regions,
                    "Marcação de dano manual recebida durante a captura. Serve como Ground Truth para treinamento."
                ),
            )
    result["analysis_id"] = analysis_id
    result["heatmap_path"] = rel_heatmap
    result["heatmap_url"]  = _heatmap_url(rel_heatmap)
    return result


@app.route("/api/aircraft/<int:aircraft_id>/areas/<int:area_id>/analyze", methods=["POST"])
def analyze_area(aircraft_id: int, area_id: int):
    """Dispara análise IA para uma área específica."""
    data     = request.get_json(force=True) or {}
    position = (data.get("position") or "").strip().upper() or None
    phase    = (data.get("phase") or "Recebimento").strip()
    try:
        result = _run_area_analysis(aircraft_id, area_id, position, phase)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Falha na análise: {e}"}), 500


@app.route("/api/aircraft/<int:aircraft_id>/analyze", methods=["POST"])
def analyze_aircraft(aircraft_id: int):
    """Dispara análise IA para todas as áreas com BEFORE+AFTER do avião."""
    data     = request.get_json(force=True) or {}
    position = (data.get("position") or "").strip().upper() or None
    phase    = (data.get("phase") or "Recebimento").strip()

    with db_conn() as conn:
        if position:
            area_ids = fetchall(
                conn,
                f"SELECT DISTINCT area_id FROM inspection_photos WHERE aircraft_id={PH} AND position={PH} AND phase={PH}",
                (aircraft_id, position, phase),
            )
        else:
            area_ids = fetchall(
                conn,
                f"SELECT DISTINCT area_id FROM inspection_photos WHERE aircraft_id={PH} AND phase={PH}",
                (aircraft_id, phase),
            )

    results = []
    for row in area_ids:
        aid = row["area_id"]
        try:
            r = _run_area_analysis(aircraft_id, aid, position, phase)
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
    row["heatmap_url"] = _heatmap_url(row.get("heatmap_path"))
    return jsonify(row)


@app.route("/api/aircraft/<int:aircraft_id>/areas/<int:area_id>/analyses")
def list_area_analyses(aircraft_id: int, area_id: int):
    """Lista análises desta área, mais recente primeiro."""
    position = request.args.get("position") or None
    with db_conn() as conn:
        if position:
            rows = fetchall(
                conn,
                f"SELECT id, final_score, status, heatmap_path, created_at "
                f"FROM analyses WHERE aircraft_id={PH} AND area_id={PH} AND position={PH} "
                f"ORDER BY created_at DESC",
                (aircraft_id, area_id, position.upper()),
            )
        else:
            rows = fetchall(
                conn,
                f"SELECT id, final_score, status, heatmap_path, created_at "
                f"FROM analyses WHERE aircraft_id={PH} AND area_id={PH} "
                f"ORDER BY created_at DESC",
                (aircraft_id, area_id),
            )
    for r in rows:
        r["heatmap_url"] = _heatmap_url(r.get("heatmap_path"))
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
        pos_filter = request.args.get("position")
        phase_filter = request.args.get("phase") or "Recebimento"
        
        with db_conn() as conn:
            aircraft = fetchone(conn, f"SELECT * FROM aircraft WHERE id={PH}", (aircraft_id,))
            
            query = f"""
                SELECT a.*, ar.name as area_name, 
                pb.file_path as before_path, pa.file_path as after_path,
                pb.has_manual_damage as b_md, pb.manual_damage_regions as b_md_reg,
                pa.has_manual_damage as a_md, pa.manual_damage_regions as a_md_reg
                FROM analyses a 
                JOIN areas ar ON ar.id = a.area_id 
                LEFT JOIN inspection_photos pb ON pb.id = a.before_photo_id 
                LEFT JOIN inspection_photos pa ON pa.id = a.after_photo_id 
                WHERE a.aircraft_id={PH} AND a.phase={PH}
            """
            params = [aircraft_id, phase_filter]
            if pos_filter:
                query += f" AND a.position={PH}"
                params.append(pos_filter)
                
            query += " ORDER BY a.created_at DESC"
            analyses = fetchall(conn, query, tuple(params))

        if not aircraft:
            return jsonify({"error": "Aeronave não encontrada"}), 404
            
        # Filtrar para manter apenas a última análise por (área, posição)
        unique_analyses = []
        seen = set()
        for a in analyses:
            key = (a["area_id"], a.get("position"))
            if key not in seen:
                seen.add(key)
                unique_analyses.append(a)
        analyses = unique_analyses

        if not analyses:
            return jsonify({"error": "Sem análises para gerar relatório"}), 404

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # ── Cabeçalho ──
        pdf.set_font("Helvetica", "B", 20)
        pdf.set_text_color(26, 86, 219)   # azul Embraer
        pdf.cell(0, 12, "EMBRAER - AeroInspect", ln=True, align="C")
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(0, 8, f"Fase de Inspecao: {phase_filter}", ln=True, align="C")
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(60, 60, 60)
        pdf.cell(0, 8, f"Relatorio de Inspecao - Aeronave: {aircraft['serial']} ({aircraft['name']})", ln=True, align="C")
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
        pdf.cell(60, 7, f"Total de areas: {total}")
        pdf.set_text_color(16, 120, 50)
        pdf.cell(60, 7, f"Integras: {ok_count}")
        pdf.set_text_color(200, 30, 30)
        pdf.cell(60, 7, f"Com diferenca: {damaged}", ln=True)
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
            status = a["status"] or "-"
            ok = status == "OK"
            pdf.set_text_color(16, 100, 40) if ok else pdf.set_text_color(180, 20, 20)
            row = [
                (a.get("area_name") or "")[:30],
                f"{a['emb_score']:.3f}",
                f"{a['orb_score']:.3f}",
                f"{a['final_score']:.3f}",
                "Integro" if ok else "[!] Diferenca detectada",
            ]
            for i, cell in enumerate(row):
                pdf.cell(col_w[i], 7, cell, border=1, align="C" if i > 0 else "L")
            pdf.ln()
            pdf.set_text_color(30, 30, 30)

        pdf.ln(8)
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(0, 6, "Este relatorio foi gerado automaticamente pelo sistema AeroInspect e deve ser validado por inspetor certificado.", ln=True)

        # ── Páginas de Detalhes com Fotos ──
        import os
        from PIL import Image

        def get_img_h(path, target_w):
            try:
                with Image.open(path) as im:
                    w, h = im.size
                    return target_w * (h / w)
            except:
                return 75

        for a in analyses:
            pdf.add_page()
            
            pos_text = f" | {a['position']}" if a.get('position') else ""
            pdf.set_font("Helvetica", "B", 14)
            pdf.set_text_color(30, 30, 30)
            pdf.cell(0, 10, f"Detalhes da Inspecao: {a.get('area_name', '')}{pos_text}", ln=True, align="C")
            
            ok = a["status"] == "OK"
            pdf.set_font("Helvetica", "B", 12)
            if ok:
                pdf.set_text_color(16, 120, 50)
                pdf.cell(0, 8, "Status: Integro", ln=True, align="C")
            else:
                pdf.set_text_color(200, 30, 30)
                pdf.cell(0, 8, "Status: [!] Diferenca Detectada", ln=True, align="C")
                
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(60, 60, 60)
            pdf.cell(0, 6, f"Score Semantico: {a['emb_score']:.3f}   |   Score ORB: {a['orb_score']:.3f}   |   Score Final: {a['final_score']:.3f}", ln=True, align="C")
            pdf.ln(6)
            
            before_path = a.get("before_path")
            after_path = a.get("after_path")
            heatmap_path = a.get("heatmap_path")
            
            w = 90
            x1 = 12
            x2 = 108
            
            # Print titles for before and after
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(80, 80, 80)
            pdf.set_x(x1)
            pdf.cell(w, 6, "ANTES", align="C")
            pdf.set_x(x2)
            pdf.cell(w, 6, "DEPOIS", ln=True, align="C")
            
            y_imgs = pdf.get_y()
            
            max_img_h = 0
            def _draw_damage(p, is_md, md_reg):
                if not is_md or not md_reg: return p
                try:
                    regs = json.loads(md_reg)
                    if not regs: return p
                    from PIL import ImageDraw
                    with Image.open(p) as im:
                        im = im.convert("RGB")
                        draw = ImageDraw.Draw(im)
                        w, h = im.size
                        for r in regs:
                            x = r['x'] * w
                            y = r['y'] * h
                            rw = r['w'] * w
                            rh = r['h'] * h
                            # Draw thick red rectangle
                            for i in range(3):
                                draw.rectangle([x-i, y-i, x+rw+i, y+rh+i], outline="red")
                        out_p = p.replace(".jpg", "_dmg.jpg")
                        im.save(out_p)
                        return out_p
                except Exception:
                    pass
                return p

            try:
                if before_path and os.path.exists(before_path):
                    bp = _draw_damage(before_path, a.get("b_md"), a.get("b_md_reg"))
                    h_b = get_img_h(bp, w)
                    pdf.image(bp, x=x1, y=y_imgs, w=w)
                    max_img_h = max(max_img_h, h_b)
                if after_path and os.path.exists(after_path):
                    ap = _draw_damage(after_path, a.get("a_md"), a.get("a_md_reg"))
                    h_a = get_img_h(ap, w)
                    pdf.image(ap, x=x2, y=y_imgs, w=w)
                    max_img_h = max(max_img_h, h_a)
            except Exception as e:
                pdf.set_xy(x1, y_imgs)
                pdf.cell(0, 10, f"Erro ao carregar imagens: {e}", ln=True)
                
            pdf.set_y(y_imgs + max_img_h + 8)
            
            if heatmap_path and os.path.exists(heatmap_path):
                pdf.set_font("Helvetica", "B", 11)
                pdf.set_text_color(30, 30, 30)
                pdf.cell(0, 8, "Mapa de Calor (Heatmap)", ln=True, align="C")
                pdf.ln(2)
                heatmap_w = 120
                heatmap_x = (210 - heatmap_w) / 2
                try:
                    # O heatmap_path aponta para uma imagem composta (Antes | Depois | Heatmap)
                    # Vamos recortar apenas o terço final (o heatmap puro) para o PDF
                    with Image.open(heatmap_path) as im:
                        iw, ih = im.size
                        cropped = im.crop((iw * 2 // 3, 0, iw, ih))
                        temp_path = heatmap_path.replace(".jpg", "_crop.jpg")
                        cropped.save(temp_path)
                    
                    pdf.image(temp_path, x=heatmap_x, y=pdf.get_y(), w=heatmap_w)
                except Exception as e:
                    pdf.cell(0, 10, f"Erro ao processar heatmap", ln=True, align="C")

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

    class_ok    = bool(data.get("classification_correct"))
    location_ok = bool(data.get("damage_location_correct"))
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


# ─── AI Insights (Gemini) ───────────────────────────────────────────────────

# Configuração do Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip().strip('"').strip("'")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

@app.route("/api/ai/query", methods=["POST"])
def ai_query():
    if not GEMINI_API_KEY:
        return jsonify({"error": "Chave GEMINI_API_KEY não configurada no servidor."}), 500

    data = request.get_json(force=True)
    question = data.get("question")
    if not question:
        return jsonify({"error": "Pergunta não informada"}), 400

    # 1. Preparar o prompt com o esquema para gerar SQL
    current_schema = SCHEMA_PG if IS_POSTGRES else SCHEMA_SQLITE
    db_engine = "PostgreSQL" if IS_POSTGRES else "SQLite"

    schema_prompt = f"""
    Você é um analista de dados especialista em inspeção de aeronaves AeroInspect.
    O banco de dados ({db_engine}) tem o seguinte esquema:
    {current_schema}

    Instruções para geração de SQL:
    1. O usuário fará perguntas sobre inspeções, danos e fotos.
    2. CONCEITO DE DANO:
       - Um "Dano Manual" é identificado quando `inspection_photos.has_damage_check = 2`.
       - Um "Dano por IA" é identificado quando `analyses.status = 'Dano Detectado'`.
       - `has_damage_check = 0` significa "Pendente" (não avaliado).
       - `has_damage_check = 1` significa "Sem Dano".
    3. Para responder sobre danos em um avião, verifique SEMPRE as duas tabelas (`inspection_photos` e `analyses`).
    4. Use JOIN com a tabela `areas` para obter o nome da região (`areas.name`) e com `aircraft` para filtrar pelo `serial`.
    5. Se o usuário pedir fotos, certifique-se de incluir `file_path` (ou `heatmap_path`) na query.
    6. Gere APENAS uma query SQL 'SELECT' válida. Não retorne markdown, apenas o texto da query.
    7. No Postgres, booleanos são TRUE/FALSE. No SQLite, use 1/0.

    Pergunta do usuário: {question}
    SQL:"""

    try:
        # Tenta uma sequência de nomes para máxima compatibilidade (Sync com financas-bot-saas)
        model_names = ['gemini-flash-latest', 'gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']
        response = None
        response = None
        model = None
        
        for m_name in model_names:
            try:
                print(f"DEBUG: Tentando Gemini modelo {m_name}...")
                model = genai.GenerativeModel(m_name)
                print(f"DEBUG: Modelo {m_name} instanciado. Gerando conteúdo...")
                response = model.generate_content(schema_prompt)
                print(f"DEBUG: Resposta recebida de {m_name}")
                if response: break
            except Exception as e:
                print(f"⚠️ Erro ao tentar modelo {m_name}: {type(e).__name__}: {str(e)}")
                continue
        
        if not response:
            print("❌ Erro: Todos os modelos Gemini falharam.")
            return jsonify({"error": "Nenhum modelo Gemini disponível no momento. Verifique logs do servidor."}), 500
            
        print("DEBUG: Analisando candidatos da resposta...")
        if not response.candidates:
            print("❌ Erro: Resposta sem candidatos (provável filtro de segurança)")
            return jsonify({"answer": "A IA não conseguiu gerar uma query. Pode ser um filtro de segurança do Google."})
            
        try:
            sql_query = response.text.strip().replace('```sql', '').replace('```', '').strip()
            print(f"DEBUG: SQL Gerado: {sql_query}")
        except ValueError as ve:
            print(f"❌ Erro ao ler response.text: {ve}")
            return jsonify({"answer": "A resposta da IA foi bloqueada pelos filtros de segurança. Tente reformular a pergunta."})

        if sql_query.startswith("ERROR"):
            return jsonify({"answer": "Desculpe, não encontrei dados suficientes para responder a essa pergunta."})

        # Segurança: Validar se é apenas SELECT
        if not sql_query.lower().startswith("select"):
            return jsonify({"error": f"A IA gerou uma query inválida: {sql_query}"}), 500

        # 2. Executar a query
        results = []
        try:
            with db_conn() as conn:
                results = fetchall(conn, sql_query)
        except Exception as db_e:
            print(f"Erro ao executar SQL da IA: {db_e} | Query: {sql_query}")
            return jsonify({"error": f"Erro no banco de dados ao processar a pergunta da IA: {db_e}"}), 500

        # 3. Formatar a resposta final em texto
        format_prompt = f"""
        Você é o AeroInspect Intelligence, um assistente técnico de inspeção de aeronaves.
        Responda à pergunta do usuário baseando-se EXCLUSIVAMENTE nos dados fornecidos do banco de dados.

        Pergunta: "{question}"
        Dados encontrados (JSON): {results}
        
        DIRETRIZES DE RESPOSTA:
        1. Se os dados mostram danos (`has_damage_check = 2` ou status 'Dano Detectado'), liste-os claramente por posição e região.
        2. Se o usuário pediu imagens e os dados contêm `file_path` ou `heatmap_path`, você DEVE incluí-las.
        3. Para cada imagem, use a URL começando com '/' (ex: "/data/inspections/...") e coloque-a entre aspas duplas em uma nova linha.
        4. O sistema irá renderizar automaticamente qualquer string que comece com "/data/".
        5. Se não houver dados, diga que não encontrou registros para os critérios informados.
        6. Mantenha um tom profissional, técnico e direto.
        7. No final, adicione: "Você deseja que eu gere um gráfico sobre?"
        """
        
        try:
            final_response = model.generate_content(format_prompt)
            if not final_response or not final_response.candidates:
                 return jsonify({"answer": "A IA processou os dados mas não conseguiu formatar a resposta por filtros de segurança."})
            answer_text = final_response.text.strip()
        except (ValueError, Exception) as fe:
            print(f"Erro ao formatar resposta final: {fe}")
            # Fallback se a formatação falhar
            return jsonify({
                "answer": f"Aqui estão os dados encontrados: {results}. Você deseja que eu gere um gráfico sobre?",
                "sql": sql_query if app.debug else None
            })

        return jsonify({
            "answer": answer_text,
            "sql": sql_query if app.debug else None
        })

    except Exception as e:
        print(f"Erro AI Query: {e}")
        return jsonify({"error": str(e)}), 500


# ─── Entry ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5051))
    print(f"\n🛩️  AeroInspect → http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
