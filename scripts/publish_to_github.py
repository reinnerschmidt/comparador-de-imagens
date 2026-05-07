from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
from typing import Any
from urllib import error, request

API_BASE = "https://api.github.com"

DEFAULT_EXCLUDES = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    "node_modules",
    "dist",
    "build",
}

DEFAULT_SKIP_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
}


def api_request(
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    req = request.Request(url=url, method=method, data=body)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if body is not None:
        req.add_header("Content-Type", "application/json")

    try:
        with request.urlopen(req) as resp:
            data = resp.read().decode("utf-8")
            if not data:
                return {}
            return json.loads(data)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub API error {exc.code} on {method} {url}\n{detail}"
        ) from exc


def get_authenticated_user(token: str) -> str:
    data = api_request("GET", f"{API_BASE}/user", token)
    return data["login"]


def create_repository(
    token: str,
    name: str,
    description: str,
    private: bool,
) -> dict[str, Any]:
    payload = {
        "name": name,
        "description": description,
        "private": private,
        "auto_init": True,
    }
    try:
        return api_request("POST", f"{API_BASE}/user/repos", token, payload)
    except RuntimeError as exc:
        # If the repository already exists, continue using it.
        if " 422 " in str(exc) or "already exists" in str(exc):
            return api_request("GET", f"{API_BASE}/repos/{get_authenticated_user(token)}/{name}", token)
        raise


def should_skip(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)

    for part in rel.parts:
        if part in DEFAULT_EXCLUDES:
            return True
        if part.endswith(".egg-info"):
            return True

    if path.is_file() and path.suffix.lower() in DEFAULT_SKIP_SUFFIXES:
        return True

    return False


def collect_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if should_skip(path, root):
            continue
        files.append(path)
    files.sort()
    return files


def upload_file_contents(
    token: str,
    owner: str,
    repo: str,
    branch: str,
    rel_path: str,
    raw_bytes: bytes,
    message: str,
) -> None:
    b64 = base64.b64encode(raw_bytes).decode("ascii")
    api_request(
        "PUT",
        f"{API_BASE}/repos/{owner}/{repo}/contents/{rel_path}",
        token,
        {
            "message": message,
            "content": b64,
            "branch": branch,
        },
    )


def publish_files(
    token: str,
    owner: str,
    repo: str,
    branch: str,
    root: Path,
    files: list[Path],
    base_message: str,
) -> None:
    for file_path in files:
        rel = file_path.relative_to(root).as_posix()
        upload_file_contents(
            token=token,
            owner=owner,
            repo=repo,
            branch=branch,
            rel_path=rel,
            raw_bytes=file_path.read_bytes(),
            message=f"{base_message}: {rel}",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cria repo no GitHub e publica o projeto sem Git instalado."
    )
    parser.add_argument("--repo", required=True,
                        help="Nome do novo repositório")
    parser.add_argument(
        "--owner",
        default="",
        help="Owner/usuario GitHub (se vazio, usa usuario autenticado)",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("GITHUB_TOKEN", ""),
        help="Token pessoal GitHub (ou use env GITHUB_TOKEN)",
    )
    parser.add_argument(
        "--description",
        default="Projeto comparador de imagens",
        help="Descrição do repositório",
    )
    parser.add_argument(
        "--private",
        action="store_true",
        help="Cria repositório privado (padrão: público)",
    )
    parser.add_argument(
        "--branch",
        default="main",
        help="Nome da branch inicial",
    )
    parser.add_argument(
        "--message",
        default="Initial commit",
        help="Mensagem do commit inicial",
    )
    parser.add_argument(
        "--project-dir",
        default=".",
        help="Diretório do projeto a publicar",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.token:
        raise RuntimeError(
            "Token não informado. Use --token ou defina GITHUB_TOKEN."
        )

    project_root = Path(args.project_dir).resolve()
    if not project_root.exists():
        raise RuntimeError(
            f"Diretório do projeto não encontrado: {project_root}")

    owner = args.owner or get_authenticated_user(args.token)

    print("[1/5] Criando repositório...")
    repo_data = create_repository(
        token=args.token,
        name=args.repo,
        description=args.description,
        private=args.private,
    )

    print("[2/5] Coletando arquivos...")
    files = collect_files(project_root)
    if not files:
        raise RuntimeError("Nenhum arquivo encontrado para publicar.")
    print(f"Arquivos selecionados: {len(files)}")

    print("[3/5] Publicando arquivos no GitHub...")
    publish_files(
        token=args.token,
        owner=owner,
        repo=args.repo,
        branch=args.branch,
        root=project_root,
        files=files,
        base_message=args.message,
    )

    print("[4/5] Consultando commit mais recente...")
    commit_data = api_request(
        "GET",
        f"{API_BASE}/repos/{owner}/{args.repo}/commits/{args.branch}",
        args.token,
    )
    commit_sha = commit_data.get("sha", "")

    print(f"[5/5] Branch ativa: {args.branch}")

    print("Publicação concluída com sucesso.")
    print(
        f"Repositório: {repo_data.get('html_url', f'https://github.com/{owner}/{args.repo}')}")
    if commit_sha:
        print(f"Commit: {commit_sha}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
