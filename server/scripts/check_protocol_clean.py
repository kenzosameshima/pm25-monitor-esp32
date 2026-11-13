"""Confere, antes da rodada final, que o protocolo de avaliação e a grade estão commitados e sem alterações.

O protocolo (docs/protocolo-de-avaliacao.md) só vale se cada mudança for commitada antes de rodar de novo, e a
grade de hiperparâmetros (docs/grade-hiperparametros.json) tem de estar registrada antes de ver os resultados.
Este script falha se um dos dois arquivos não existir, não estiver no último commit ou tiver alterações não
commitadas (no arquivo ou já preparadas no índice). Quando passa, mostra o commit atual e o último commit de
cada arquivo, para registrar junto dos resultados. Só lê o repositório.

Saída: 0 se os dois arquivos estão limpos; 1 se algum não está; 2 se a pasta não é um repositório git ou o git
não está instalado.

Uso: python -m scripts.check_protocol_clean [--repo PASTA]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROTOCOL_FILES = ("docs/protocolo-de-avaliacao.md", "docs/grade-hiperparametros.json")
REPO_ROOT = Path(__file__).resolve().parents[2]


class NotARepository(RuntimeError):
    """A pasta não é um repositório git, ou o git não pôde ser executado."""


def _git(repo: Path, *args: str) -> str:
    try:
        done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")
    except OSError as exc:
        raise NotARepository(f"não foi possível executar o git: {exc}") from None
    if done.returncode != 0:
        raise NotARepository(done.stderr.strip() or f"git {' '.join(args)} falhou")
    return done.stdout.strip()


def problems(repo: Path, files: tuple[str, ...] = PROTOCOL_FILES) -> list[str]:
    """Uma frase por arquivo que impede a rodada; lista vazia quando todos estão commitados e sem alterações."""
    found = []
    for name in files:
        if not (repo / name).is_file():
            found.append(f"{name}: o arquivo não existe")
        elif not _git(repo, "ls-tree", "HEAD", "--", name):
            found.append(f"{name}: não está commitado")
        elif _git(repo, "status", "--porcelain", "--", name):
            found.append(f"{name}: tem alterações não commitadas")
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=str(REPO_ROOT), help="pasta do repositório (padrão: a deste script)")
    args = ap.parse_args(argv)
    try:
        repo = Path(_git(Path(args.repo), "rev-parse", "--show-toplevel"))
        head = _git(repo, "rev-parse", "HEAD")
        found = problems(repo)
        commits = {} if found else {name: _git(repo, "log", "-1", "--format=%H %cI", "--", name)
                                    for name in PROTOCOL_FILES}
    except NotARepository as exc:
        print(f"Erro: {args.repo} não é um repositório git utilizável ({exc})", file=sys.stderr)
        return 2
    if found:
        for line in found:
            print(f"Erro: {line}", file=sys.stderr)
        print("A rodada final não deve rodar: commite a mudança, com o motivo, ou desfaça-a.", file=sys.stderr)
        return 1
    print(f"Protocolo e grade commitados e sem alterações. Commit atual: {head}")
    for name, commit in commits.items():
        print(f"  {name}: último commit {commit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
