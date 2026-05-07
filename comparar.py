#!/usr/bin/env python3
"""Compara duas imagens diretamente e exibe o resultado.

Uso:
    python comparar.py <foto_antes> <foto_depois>

Exemplos:
    python comparar.py foto_antes.jpg foto_depois.jpg
    python comparar.py data/reference/console_central.jpeg data/inspection/console_central.jpeg
"""
import sys
import os

# Adiciona src ao path para importar os módulos do projeto
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from preprocessing.image_loader import _load_with_cv2
from similarity import embedding, orb
from fusion import decision


def comparar(ref_path: str, cur_path: str) -> None:
    print(f"\n{'='*50}")
    print(f"  ANTES  : {ref_path}")
    print(f"  DEPOIS : {cur_path}")
    print(f"{'='*50}")

    if not os.path.exists(ref_path):
        print(f"❌ Arquivo não encontrado: {ref_path}")
        return
    if not os.path.exists(cur_path):
        print(f"❌ Arquivo não encontrado: {cur_path}")
        return

    print("⏳ Carregando imagens...")
    img_ref = _load_with_cv2(ref_path)
    img_cur = _load_with_cv2(cur_path)

    print("🧠 Analisando com IA (EfficientNetB0)...")
    emb_score = embedding.compute_embedding_score(img_ref, img_cur)
    orb_score = orb.compute_orb_score(img_ref, img_cur)

    final_score, recommendation = decision.fuse_and_decide(emb_score, orb_score)

    print(f"\n  📊 Similaridade Semântica (Embedding) : {emb_score:.4f}")
    print(f"  📊 Correspondência de Pontos (ORB)    : {orb_score:.4f}")
    print(f"  📊 Score Final                        : {final_score:.4f}")
    print(f"\n  {'✅' if 'Nenhuma' in recommendation else '⚠️ '} {recommendation}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    comparar(sys.argv[1], sys.argv[2])
