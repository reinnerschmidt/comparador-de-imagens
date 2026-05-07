from __future__ import annotations

import argparse

from .comparador import comparar_arquivos


def main() -> int:
    parser = argparse.ArgumentParser(description="Compara duas imagens por conteúdo binário")
    parser.add_argument("imagem_a", help="Caminho da primeira imagem")
    parser.add_argument("imagem_b", help="Caminho da segunda imagem")
    args = parser.parse_args()

    iguais = comparar_arquivos(args.imagem_a, args.imagem_b)
    if iguais:
        print("As imagens são iguais.")
        return 0

    print("As imagens são diferentes.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
