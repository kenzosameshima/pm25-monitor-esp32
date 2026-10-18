"""Os wrappers das tarefas agendadas do Windows gravam os logs em UTF-8."""

from pathlib import Path

import pytest

WRAPPERS = sorted((Path(__file__).parent.parent / "deploy" / "windows").glob("run-*.cmd"))


@pytest.mark.parametrize("wrapper", WRAPPERS, ids=lambda p: p.name)
def test_wrapper_ativa_o_modo_utf8_antes_do_python(wrapper):
    # Sem o modo UTF-8, a saída redirecionada para o log usa cp1252, que não codifica emojis.
    lines = wrapper.read_text(encoding="ascii").splitlines()
    python = next(i for i, line in enumerate(lines) if "python.exe" in line)
    assert "set PYTHONUTF8=1" in lines[:python]
