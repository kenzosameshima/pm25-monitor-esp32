"""O tema do dashboard: segue o sistema (claro ou escuro) e as cores têm contraste de texto sobre o fundo."""

from pathlib import Path

import pytest

tomli = pytest.importorskip("tomli")  # o Python 3.10 ainda não traz tomllib; o Streamlit já instala o tomli

CONFIG = Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml"
MODES = ["light", "dark"]


def luminance(color: str) -> float:
    """Luminância relativa de uma cor "#rrggbb", como no WCAG 2.1."""
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.fixture(scope="module")
def theme() -> dict:
    return tomli.loads(CONFIG.read_text(encoding="utf-8"))["theme"]


def test_contraste_conhecido_do_wcag():
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast("#777777", "#ffffff") == pytest.approx(4.48, abs=0.01)   # o cinza que quase passa


@pytest.mark.parametrize("mode", MODES)
def test_o_tema_define_o_modo_claro_e_o_escuro(theme, mode):
    assert {"backgroundColor", "secondaryBackgroundColor", "textColor", "primaryColor"} <= set(theme[mode])


@pytest.mark.parametrize("mode", MODES)
def test_o_texto_tem_contraste_de_texto_comum_sobre_o_fundo_e_sobre_o_cartao(theme, mode):
    colors = theme[mode]
    assert contrast(colors["textColor"], colors["backgroundColor"]) >= 7
    assert contrast(colors["textColor"], colors["secondaryBackgroundColor"]) >= 7


@pytest.mark.parametrize("mode", MODES)
def test_a_cor_de_interacao_tem_contraste_de_texto_sobre_o_fundo(theme, mode):
    colors = theme[mode]
    assert contrast(colors["primaryColor"], colors["backgroundColor"]) >= 4.5
