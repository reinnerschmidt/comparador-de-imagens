#!/usr/bin/env python3
"""Gerador de pares sintéticos de superfície de aeronave.

Cria imagens programáticas de superfície metálica (com rebites e linhas de
painel) e gera pares (referência, inspeção) com e sem danos simulados.
Salva em data/reference/ e data/inspection/ e gera data/labeled/pairs.csv
com os rótulos para calibração do threshold.

Uso:
    python scripts/generate_synthetic_data.py
    python scripts/generate_synthetic_data.py --n-pairs 60 --seed 123
"""
from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

import cv2
import numpy as np

# ─── Defaults ─────────────────────────────────────────────────────────────────
IMAGE_SIZE = (256, 256)
DEFAULT_N_PAIRS = 40
DEFAULT_SEED = 42

PROJECT_ROOT   = Path(__file__).parent.parent

OUT_REFERENCE = PROJECT_ROOT / "data/reference"
OUT_INSPECTION = PROJECT_ROOT / "data/inspection"
OUT_LABELED    = PROJECT_ROOT / "data/labeled"


# ─── Surface generation ───────────────────────────────────────────────────────

def generate_aircraft_surface(rng: np.random.Generator) -> np.ndarray:
    """Textura sintética de superfície metálica: gradiente + rebites + linhas de painel."""
    h, w = IMAGE_SIZE
    # Base cinza metálico com leve gradiente vertical
    base_val = rng.integers(160, 200)
    surface = np.full((h, w, 3), base_val, dtype=np.float32)
    grad = np.linspace(-15, 15, h, dtype=np.float32)[:, None, None]
    surface += grad

    # Ruído de textura metálica (baixa frequência)
    noise = rng.standard_normal((h, w)).astype(np.float32) * 6
    noise = cv2.GaussianBlur(noise, (11, 11), 4)
    surface += noise[:, :, None]

    surface = np.clip(surface, 0, 255).astype(np.uint8)

    # Linhas de painel (junções entre chapas)
    panel_step = rng.integers(70, 90)
    panel_color = max(0, int(base_val) - 40)
    for y in range(0, h, panel_step):
        surface[y: y + 2, :] = panel_color
    for x in range(0, w, panel_step):
        surface[:, x: x + 2] = panel_color

    # Rebites nos painéis
    rivet_step = 18
    rivet_color = max(0, int(base_val) - 55)
    for y in range(rivet_step // 2, h, rivet_step):
        for x in range(rivet_step // 2, w, rivet_step):
            jitter_y = int(rng.integers(-2, 2))
            jitter_x = int(rng.integers(-2, 2))
            cy = min(max(y + jitter_y, 2), h - 3)
            cx = min(max(x + jitter_x, 2), w - 3)
            cv2.circle(surface, (cx, cy), 2, (rivet_color,) * 3, -1)

    return surface


# ─── Damage generators ────────────────────────────────────────────────────────

def apply_dent(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Amassado: região oval escurecida com gradiente suave."""
    out = img.copy().astype(np.float32)
    h, w = img.shape[:2]
    cx = int(rng.integers(50, w - 50))
    cy = int(rng.integers(50, h - 50))
    rx = int(rng.integers(15, 35))
    ry = int(rng.integers(10, 25))

    ys, xs = np.ogrid[:h, :w]
    dist = ((xs - cx) / rx) ** 2 + ((ys - cy) / ry) ** 2
    inside = dist <= 1.0
    factor = (0.55 + 0.35 * dist[inside])[:, None]  # [N,1] broadcasts over RGB
    out[inside] *= factor
    return np.clip(out, 0, 255).astype(np.uint8)


def apply_scratch(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Arranhão: linha fina e escura."""
    out = img.copy()
    h, w = img.shape[:2]
    x1 = int(rng.integers(20, w - 20))
    y1 = int(rng.integers(20, h - 20))
    length = int(rng.integers(40, 110))
    angle = float(rng.uniform(0, np.pi))
    x2 = int(np.clip(x1 + length * np.cos(angle), 0, w - 1))
    y2 = int(np.clip(y1 + length * np.sin(angle), 0, h - 1))
    thickness = int(rng.integers(1, 3))
    scratch_color = (50, 45, 40)
    cv2.line(out, (x1, y1), (x2, y2), scratch_color, thickness)
    return out


def apply_corrosion(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Corrosão: mancha laranja-marrom irregular."""
    out = img.copy().astype(np.float32)
    h, w = img.shape[:2]
    cx = int(rng.integers(50, w - 50))
    cy = int(rng.integers(50, h - 50))
    radius = int(rng.integers(18, 42))

    # Máscara circular + ruído para bordas irregulares
    mask_circle = np.zeros((h, w), dtype=np.float32)
    cv2.circle(mask_circle, (cx, cy), radius, 1.0, -1)

    noise = rng.random((h, w)).astype(np.float32)
    noise = cv2.GaussianBlur(noise, (21, 21), 8)
    noise = (noise - noise.min()) / (noise.max() - noise.min() + 1e-8)

    corr_mask = (mask_circle > 0.5) & (noise > 0.42)
    rust = np.array([130, 75, 35], dtype=np.float32)
    alpha = float(rng.uniform(0.5, 0.75))
    out[corr_mask] = (1 - alpha) * out[corr_mask] + alpha * rust
    return np.clip(out, 0, 255).astype(np.uint8)


DAMAGE_FUNCS = {
    "dent": apply_dent,
    "scratch": apply_scratch,
    "corrosion": apply_corrosion,
}


# ─── Inspection augmentations (variações realistas sem dano) ──────────────────

def apply_illumination_shift(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Simula variação de iluminação entre inspeções (±15%)."""
    factor = float(rng.uniform(0.88, 1.15))
    return np.clip(img.astype(np.float32) * factor, 0, 255).astype(np.uint8)


def apply_small_rotation(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Rotação de até ±2° — simula leve variação de ângulo de câmera."""
    angle = float(rng.uniform(-2.0, 2.0))
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, M, (w, h))


def apply_sensor_noise(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Ruído Gaussiano leve — simula variação de sensor."""
    noise = rng.standard_normal(img.shape).astype(np.float32) * 5
    return np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)


# ─── Main generator ───────────────────────────────────────────────────────────

def generate_pair(
    idx: int,
    rng: np.random.Generator,
    damage_type: str | None,
) -> tuple[np.ndarray, np.ndarray]:
    """Gera um par (referência, inspeção). damage_type=None → sem dano."""
    reference = generate_aircraft_surface(rng)

    # Inspeção sempre tem pequenas variações realistas
    inspection = apply_illumination_shift(reference.copy(), rng)
    inspection = apply_small_rotation(inspection, rng)
    inspection = apply_sensor_noise(inspection, rng)

    if damage_type is not None:
        inspection = DAMAGE_FUNCS[damage_type](inspection, rng)

    return reference, inspection


def run(n_pairs: int, seed: int) -> None:
    rng = np.random.default_rng(seed)
    random.seed(seed)

    OUT_REFERENCE.mkdir(parents=True, exist_ok=True)
    OUT_INSPECTION.mkdir(parents=True, exist_ok=True)
    OUT_LABELED.mkdir(parents=True, exist_ok=True)

    damage_types = list(DAMAGE_FUNCS.keys())  # dent, scratch, corrosion
    rows: list[dict] = []

    # Distribuição: 50% sem dano, 50% com dano (balanceado)
    n_damaged = n_pairs // 2
    n_clean = n_pairs - n_damaged

    pairs_config: list[str | None] = [None] * n_clean
    for i in range(n_damaged):
        pairs_config.append(damage_types[i % len(damage_types)])
    rng.shuffle(pairs_config)  # type: ignore[arg-type]

    for idx, damage_type in enumerate(pairs_config, start=1):
        ref_img, insp_img = generate_pair(idx, rng, damage_type)

        ref_filename = f"surface_{idx:03d}.png"
        insp_filename = f"surface_{idx:03d}.png"

        cv2.imwrite(
            str(OUT_REFERENCE / ref_filename),
            cv2.cvtColor(ref_img, cv2.COLOR_RGB2BGR),
        )
        cv2.imwrite(
            str(OUT_INSPECTION / insp_filename),
            cv2.cvtColor(insp_img, cv2.COLOR_RGB2BGR),
        )

        label = 0 if damage_type is None else 1
        rows.append({
            "ref_path": str(OUT_REFERENCE / ref_filename),
            "insp_path": str(OUT_INSPECTION / insp_filename),
            "label": label,
            "damage_type": damage_type or "none",
        })

        status = f"[dano: {damage_type}]" if damage_type else "[sem dano]"
        print(f"  Par {idx:03d} {status}")

    csv_path = OUT_LABELED / "pairs.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["ref_path", "insp_path", "label", "damage_type"])
        writer.writeheader()
        writer.writerows(rows)

    damaged_count = sum(1 for r in rows if r["label"] == 1)
    print(f"\n✅ {n_pairs} pares gerados → {OUT_REFERENCE} / {OUT_INSPECTION}")
    print(f"   Com dano: {damaged_count} | Sem dano: {n_pairs - damaged_count}")
    print(f"   Labels  : {csv_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gerador de imagens sintéticas de aeronave")
    parser.add_argument("--n-pairs", type=int, default=DEFAULT_N_PAIRS, help="Número de pares a gerar")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Semente aleatória")
    args = parser.parse_args()

    print(f"🛩️  Gerando {args.n_pairs} pares sintéticos (seed={args.seed})...\n")
    run(args.n_pairs, args.seed)


if __name__ == "__main__":
    main()
