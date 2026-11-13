"""Figuras do capítulo de resultados, a partir dos CSVs que os outros scripts gravam em `resultados/`.

Só lê os CSVs; não abre o banco. Grava em --out-dir um PNG por figura:

- completude_diaria.png: completude da coleta por dia (completude_diaria.csv, do period_metrics);
- perfil_pm25.png: média de PM2,5 por hora do dia e por dia da semana (perfil_hora.csv e perfil_dia_semana.csv);
- dispersao_cetesb.png: nó × CETESB, hora a hora, com a reta de regressão e a linha 1:1
  (comparacao_cetesb_pares.csv, do compare_cetesb);
- previsto_observado.png: observado, persistência e Ridge no teste final (<nó>/previsao_teste.csv, do
  train_forecast).

Uma figura cujo CSV não existe, ou não tem linhas do nó, é pulada com um aviso; sem nenhuma figura, o script
termina com código 1. As figuras valem para os dados da pasta lida: rode de novo sobre a pasta da rodada final.
Requer matplotlib (requirements-figures.txt), que não faz parte do ambiente do servidor.

Uso: python -m scripts.result_figures [--results ../resultados] [--out-dir ../resultados/figuras] [--device no-01]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # sem janela: só grava arquivos
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

FIGURES = ("completude_diaria.png", "perfil_pm25.png", "dispersao_cetesb.png", "previsto_observado.png")
INK, MUTED, GRID = "#1f2933", "#6b7785", "#d9dee4"
BLUE, ORANGE = "#2a6fb0", "#c9601a"   # no máximo duas cores de série por figura; a terceira série é cinza tracejado
UNIT = "PM2,5 (µg/m³)"


class Skip(Exception):
    """A figura não pode ser feita com o que há na pasta."""


def _read(path: Path, device: str, column: str = "device_id", **kwargs) -> pd.DataFrame:
    if not path.exists():
        raise Skip(f"{path.name} não encontrado em {path.parent}")
    frame = pd.read_csv(path, **kwargs)
    frame = frame[frame[column] == device]
    if frame.empty:
        raise Skip(f"{path.name} não tem linhas do nó {device}")
    return frame


def _style(ax, ylabel: str | None = None) -> None:
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=9)
    if ylabel:
        ax.set_ylabel(ylabel, color=INK, fontsize=10)


def _brt(series: pd.Series) -> pd.Series:
    """Horários em UTC convertidos para o relógio de Brasília, sem fuso, para o eixo do gráfico."""
    return pd.to_datetime(series, utc=True).dt.tz_convert("America/Sao_Paulo").dt.tz_localize(None)


def completeness(results: Path, device: str):
    df = _read(results / "completude_diaria.csv", device, parse_dates=["data"])
    fig, ax = plt.subplots(figsize=(8, 3.2))
    ax.bar(df["data"], df["completude"] * 100, width=0.8, color=BLUE)
    ax.set_ylim(0, 100)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    _style(ax, "Completude (%)")
    ax.set_title(f"Completude diária da coleta, {device}", color=INK, fontsize=11, loc="left")
    return fig


def profile(results: Path, device: str):
    hour = _read(results / "perfil_hora.csv", device)
    weekday = _read(results / "perfil_dia_semana.csv", device)
    fig, (left, right) = plt.subplots(1, 2, figsize=(9, 3.4), sharey=True, gridspec_kw={"width_ratios": [3, 2]})
    left.plot(hour["hora"], hour["media"], color=BLUE, linewidth=2, marker="o", markersize=4)
    left.set_xticks(range(0, 24, 3))
    left.set_xlabel("Hora do dia (Brasília)", color=INK, fontsize=10)
    _style(left, UNIT)
    right.bar(weekday["dia_semana"], weekday["media"], color=BLUE, width=0.7)
    right.set_xticks(range(len(weekday)), weekday["dia_semana"], rotation=30, ha="right")
    _style(right)
    left.set_ylim(bottom=0)
    left.set_title(f"Média de PM2,5 por hora do dia e por dia da semana, {device}", color=INK, fontsize=11,
                   loc="left")
    return fig


def scatter(results: Path, device: str):
    df = _read(results / "comparacao_cetesb_pares.csv", device).dropna(subset=["pm25_no", "pm25_cetesb"])
    x, y = df["pm25_cetesb"].to_numpy(float), df["pm25_no"].to_numpy(float)
    top = float(max(x.max(), y.max())) * 1.05
    fig, ax = plt.subplots(figsize=(5.2, 5.2))
    ax.scatter(x, y, s=14, color=BLUE, alpha=0.45, linewidths=0)
    ax.plot([0, top], [0, top], color=MUTED, linewidth=1, linestyle="--", label="1:1")
    if len(df) >= 2 and np.ptp(x) > 0:
        slope, intercept = np.polyfit(x, y, 1)
        ax.plot([0, top], [intercept, intercept + slope * top], color=ORANGE, linewidth=2,
                label=f"regressão: y = {slope:.2f}x + {intercept:.1f}".replace(".", ","))
    ax.set_xlim(0, top)
    ax.set_ylim(0, top)
    ax.set_aspect("equal")
    ax.set_xlabel("CETESB, " + UNIT, color=INK, fontsize=10)
    _style(ax, f"{device}, {UNIT}")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    ax.set_title(f"Médias horárias: {device} × CETESB ({len(df)} horas)", color=INK, fontsize=11, loc="left")
    return fig


def forecast(results: Path, device: str):
    df = _read(results / device / "previsao_teste.csv", device, column="no")
    df = df.assign(hora=_brt(df["hora"])).set_index("hora")
    # Hora a hora, com as horas sem previsão em branco: a linha é interrompida em vez de ligar pontos distantes.
    df = df.reindex(pd.date_range(df.index.min(), df.index.max(), freq="h"))
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.plot(df.index, df["persistencia"], color=MUTED, linewidth=1, linestyle="--", label="Persistência")
    ax.plot(df.index, df["ridge"], color=ORANGE, linewidth=1.6, label="Ridge")
    ax.plot(df.index, df["observado"], color=BLUE, linewidth=2, label="Observado")
    ax.set_ylim(bottom=0)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    _style(ax, UNIT)
    ax.legend(frameon=False, fontsize=9, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.1))
    ax.set_title(f"Previsto × observado no teste final, {device} (hora de Brasília)", color=INK, fontsize=11,
                 loc="left")
    return fig


BUILDERS = dict(zip(FIGURES, (completeness, profile, scatter, forecast)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", default="../resultados", help="pasta com os CSVs (padrão: ../resultados)")
    ap.add_argument("--out-dir", default=None, help="pasta das figuras (padrão: <results>/figuras)")
    ap.add_argument("--device", default="no-01", help="nó das figuras (padrão: no-01)")
    ap.add_argument("--dpi", type=int, default=200)
    args = ap.parse_args(argv)
    results = Path(args.results)
    out = Path(args.out_dir) if args.out_dir else results / "figuras"

    done = 0
    for name, build in BUILDERS.items():
        try:
            fig = build(results, args.device)
        except Skip as exc:
            print(f"Aviso: {name} não foi gerada: {exc}", file=sys.stderr)
            continue
        out.mkdir(parents=True, exist_ok=True)
        fig.savefig(out / name, dpi=args.dpi, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        print(f"{name} gravada em {out.resolve()}")
        done += 1
    if not done:
        print("Erro: nenhuma figura gerada", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
