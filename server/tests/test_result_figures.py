"""Figuras do capítulo de resultados: cada uma sai dos CSVs de `resultados/`; sem o CSV, a figura é pulada."""

import pytest

pytest.importorskip("matplotlib")   # fica em requirements-figures.txt, fora do ambiente do servidor

from scripts import result_figures as rf  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n"


def write_inputs(folder):
    (folder / "no-01").mkdir(parents=True)
    (folder / "completude_diaria.csv").write_text(
        "device_id,data,leituras,esperadas,completude\n"
        "no-01,2026-10-09,1186,1440,0.8236\nno-01,2026-10-10,1440,1440,1.0\nno-02,2026-10-10,10,1440,0.0069\n",
        encoding="utf-8")
    (folder / "perfil_hora.csv").write_text(
        "device_id,hora,n,media\n" + "".join(f"no-01,{h},28,{10 + h}\n" for h in range(24)), encoding="utf-8")
    (folder / "perfil_dia_semana.csv").write_text(
        "device_id,dia_semana,n,media\nno-01,segunda,75,19.1\nno-01,terça,79,13.8\n", encoding="utf-8")
    (folder / "comparacao_cetesb_pares.csv").write_text(
        "hora_utc,device_id,pm25_no,pm25_cetesb,umidade,suspeita\n"
        + "".join(f"2026-10-09 {h:02d}:00:00+00:00,no-01,{12 + 2 * h},{5 + h},60.0,False\n" for h in range(24)),
        encoding="utf-8")
    (folder / "no-01" / "previsao_teste.csv").write_text(
        "hora,no,observado,persistencia,ridge,gboost,mlp\n"
        + "".join(f"2026-10-31T{h:02d}:00:00Z,no-01,{10 + h},{9 + h},{10.5 + h},{11 + h},{10.2 + h}\n"
                  for h in range(24)), encoding="utf-8")


def test_gera_uma_figura_png_por_csv(tmp_path, capsys):
    source, out = tmp_path / "resultados", tmp_path / "figuras"
    write_inputs(source)
    assert rf.main(["--results", str(source), "--out-dir", str(out), "--device", "no-01"]) == 0
    assert sorted(p.name for p in out.iterdir()) == sorted(rf.FIGURES)
    for name in rf.FIGURES:
        assert (out / name).read_bytes().startswith(PNG) and (out / name).stat().st_size > 5000
    assert capsys.readouterr().out.count("gravada") == len(rf.FIGURES)


def test_csv_ausente_pula_a_figura_e_avisa(tmp_path, capsys):
    source, out = tmp_path / "resultados", tmp_path / "figuras"
    write_inputs(source)
    (source / "comparacao_cetesb_pares.csv").unlink()
    assert rf.main(["--results", str(source), "--out-dir", str(out), "--device", "no-01"]) == 0
    assert not (out / "dispersao_cetesb.png").exists()
    assert len(list(out.iterdir())) == len(rf.FIGURES) - 1
    assert "comparacao_cetesb_pares.csv" in capsys.readouterr().err


def test_sem_nenhum_csv_termina_com_erro(tmp_path, capsys):
    assert rf.main(["--results", str(tmp_path), "--out-dir", str(tmp_path / "figuras")]) == 1
    assert "nenhuma figura" in capsys.readouterr().err


def test_no_sem_linhas_no_csv_pula_a_figura(tmp_path, capsys):
    source, out = tmp_path / "resultados", tmp_path / "figuras"
    write_inputs(source)
    assert rf.main(["--results", str(source), "--out-dir", str(out), "--device", "no-09"]) == 1
    assert "no-09" in capsys.readouterr().err
