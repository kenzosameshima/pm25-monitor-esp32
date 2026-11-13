"""check_protocol_clean: a rodada final só roda com o protocolo e a grade commitados e sem alterações."""

import shutil
import subprocess

import pytest

from scripts import check_protocol_clean as cpc

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="precisa do git")

PROTOCOL, GRID = cpc.PROTOCOL_FILES


def git(repo, *args):
    subprocess.run(["git", "-c", "user.name=Teste", "-c", "user.email=teste@example.com", *args],
                   cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    """Repositório com o protocolo e a grade commitados."""
    (tmp_path / "docs").mkdir()
    (tmp_path / PROTOCOL).write_text("# Protocolo\n", encoding="utf-8")
    (tmp_path / GRID).write_text('{"ridge": {"alpha": [10.0]}}\n', encoding="utf-8")
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "docs: add the protocol and the grid")
    return tmp_path


def run(repo, capsys):
    rc = cpc.main(["--repo", str(repo)])
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def test_passa_com_os_dois_arquivos_commitados_e_diz_o_commit_de_cada_um(repo, capsys):
    rc, out, err = run(repo, capsys)
    assert rc == 0 and err == ""
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    assert out.count(head) == 3                                    # o HEAD e o último commit de cada arquivo
    assert PROTOCOL in out and GRID in out


def test_falha_com_alteracao_nao_commitada(repo, capsys):
    (repo / GRID).write_text('{"ridge": {"alpha": [10.0, 1.0]}}\n', encoding="utf-8")
    rc, _, err = run(repo, capsys)
    assert rc == 1
    assert GRID in err and "alterações não commitadas" in err and PROTOCOL not in err


def test_falha_com_alteracao_so_preparada_no_indice(repo, capsys):
    (repo / PROTOCOL).write_text("# Protocolo\n\nRegra nova.\n", encoding="utf-8")
    git(repo, "add", PROTOCOL)
    rc, _, err = run(repo, capsys)
    assert rc == 1 and PROTOCOL in err and "alterações não commitadas" in err


def test_falha_com_arquivo_apagado(repo, capsys):
    (repo / GRID).unlink()
    rc, _, err = run(repo, capsys)
    assert rc == 1 and GRID in err and "não existe" in err


def test_falha_com_arquivo_fora_do_git(repo, capsys):
    git(repo, "rm", "-q", "--cached", GRID)
    git(repo, "commit", "-q", "-m", "chore: untrack the grid")
    rc, _, err = run(repo, capsys)                                # o arquivo existe, mas nenhum commit o guarda
    assert rc == 1 and GRID in err and "não está commitado" in err


def test_alteracao_em_outro_arquivo_nao_impede(repo, capsys):
    (repo / "docs" / "notas.md").write_text("rascunho\n", encoding="utf-8")
    rc, _, err = run(repo, capsys)
    assert rc == 0 and err == ""


def test_falha_fora_de_um_repositorio_git(tmp_path, capsys):
    rc, _, err = run(tmp_path, capsys)
    assert rc == 2 and "repositório git" in err
