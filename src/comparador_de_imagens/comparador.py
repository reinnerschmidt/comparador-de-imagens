from __future__ import annotations

from pathlib import Path


def comparar_arquivos(caminho_a: str | Path, caminho_b: str | Path) -> bool:
    """Compara dois arquivos de imagem por bytes e retorna True se forem idênticos."""
    arquivo_a = Path(caminho_a)
    arquivo_b = Path(caminho_b)

    if not arquivo_a.exists() or not arquivo_b.exists():
        raise FileNotFoundError("Um ou ambos os arquivos informados não existem.")

    if arquivo_a.stat().st_size != arquivo_b.stat().st_size:
        return False

    return arquivo_a.read_bytes() == arquivo_b.read_bytes()
