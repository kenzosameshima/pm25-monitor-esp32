"""Testes do dashboard com o AppTest do Streamlit: o script roda sem navegador sobre um banco sintético."""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pytest

pytest.importorskip("streamlit")
import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from app import db  # noqa: E402
from app.config import get_settings  # noqa: E402
from scripts.simulate_sensor import synthetic  # noqa: E402

DASHBOARD = str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py")


def populate(path: Path, hours: int = 30, devices=(("no-01", 1), ("no-02", 2))) -> None:
    conn = db.connect(str(path))
    db.init_db(conn)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    for device, boots in devices:
        state: dict = {}
        rows = []
        for i in range(hours * 60):
            if device == "no-02" and 1000 <= i < 1060:
                continue  # uma hora sem dados no nó 2
            ts = now - timedelta(minutes=hours * 60 - i)
            boot = 1 if (boots == 1 or i < hours * 30) else 2
            seq = i if boot == 1 else i - hours * 30
            r = synthetic(ts, state)
            rows.append({"device_id": device, "boot_id": boot, "seq": seq, "ts_sensor": db.iso(ts),
                         "ts_received": db.iso(ts), "uptime_s": 60 * i, "schema_version": "1",
                         "quality": "ok", **r})
        db.insert_batch(conn, device, rows, now)
    with conn:
        for h in range(1, 12):
            target = now.replace(minute=0) - timedelta(hours=h)
            conn.execute(
                "INSERT INTO forecasts (device_id, generated_at, target_hour, predicted_pm25, model_name, model_version)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                ("no-01", db.iso(target - timedelta(minutes=1)), db.iso(target), 15.0 + h % 3, "ridge", "v1"))
    conn.close()


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PM25_DB_PATH", str(tmp_path / "pm25.db"))
    monkeypatch.setenv("PM25_DEVICE_TOKENS", "no-01:token-do-no-01-aB3xQ9zK7pLm2Wv8Rt")
    get_settings.cache_clear()
    st.cache_data.clear()
    yield tmp_path / "pm25.db"
    get_settings.cache_clear()
    st.cache_data.clear()


def test_sem_banco_mostra_aviso(app_env):
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception
    assert "Nenhum dado" in at.warning[0].value


def test_dashboard_renderiza_as_tres_abas(app_env):
    populate(app_env)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert [t.label for t in at.tabs] == ["Status", "Séries", "Previsto × observado"]
    assert len(at.metric) == 8  # 4 indicadores por sensor; o sinal Wi-Fi vai numa linha à parte
    assert at.metric[0].label == "PM2,5"
    assert at.metric[0].delta in {"Boa", "Moderada", "Ruim", "Muito ruim", "Péssima"}  # faixa da CETESB
    assert at.metric[1].label == "PM10 (µg/m³)"
    assert not any("implausível" in c.value for c in at.caption)

    # tabela de saúde da coleta: o nó 2 teve uma hora sem dados e um reinício
    health = at.dataframe[0].value.set_index("Sensor")
    assert health.loc["no-02", "Reinícios"] == 1
    assert health.loc["no-02", "Maior lacuna"] >= 59       # o valor segue em minutos: a coluna ordena pelo tempo
    assert health.loc["no-01", "Mensagens perdidas"] == 0

    # previsto × observado: persistência e o modelo gravado, com skill score
    metrics = at.dataframe[1].value.set_index("Previsor")
    assert {"Persistência", "ridge v1"} <= set(metrics.index)
    assert "Skill score" in metrics.columns


def test_esconde_no_de_teste_e_reserva_card_do_no_cadastrado_sem_dados(app_env, monkeypatch):
    monkeypatch.setenv("PM25_DEVICE_TOKENS", "no-01:token-do-no-01-aB3xQ9zK7pLm2Wv8Rt,no-02:token-do-no-02-aB3xQ9zK7pLm2Wv8Rt,"
                                             "teste-https:token-do-teste-aB3xQ9zK7pLm2Wv8Rt")
    populate(app_env, hours=3, devices=(("no-01", 1), ("teste-https", 1)))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert [h.value for h in at.subheader] == ["no-01", "no-02"]
    assert any("aguardando instalação" in c.value for c in at.caption)
    assert len(at.metric) == 4  # só o no-01 tem leitura
    assert list(at.dataframe[0].value["Sensor"]) == ["no-01"]
    assert at.multiselect[0].options == ["no-01"]


def add_model_forecasts(path: Path, name: str, version: str, hours_ago: list[int]) -> None:
    """Previsões de `name version` do no-01 para as horas-alvo `hours_ago` horas antes da hora atual."""
    top = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    conn = db.connect(str(path))
    with conn:
        for k in hours_ago:
            target = top - timedelta(hours=k)
            conn.execute("INSERT INTO forecasts (device_id, generated_at, target_hour, predicted_pm25, model_name,"
                         " model_version) VALUES (?, ?, ?, ?, ?, ?)",
                         ("no-01", db.iso(target - timedelta(minutes=1)), db.iso(target), 15.0, name, version))
    conn.close()


def test_tabela_de_previsao_diz_que_todos_os_previsores_usam_as_mesmas_horas(app_env):
    populate(app_env)                                    # ridge v1 prevê as horas -1 a -11
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    metrics = at.dataframe[1].value.set_index("Previsor")
    assert set(metrics["Horas"]) == {11}                 # a persistência também só conta as 11 horas do modelo
    note = [c.value for c in at.caption if "mesmas 11 horas" in c.value]
    assert len(note) == 1 and "hora seguinte" in note[0] and " a " in note[0]  # horizonte e período avaliado


def test_tabela_de_previsao_avisa_quando_os_modelos_nao_tem_horas_em_comum(app_env):
    populate(app_env)
    add_model_forecasts(app_env, "ridge", "v2", [20, 21, 22])  # a versão nova não tem hora em comum com a v1
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert not any("mesmas 11 horas" in c.value for c in at.caption)
    assert any("nas horas em que tem previsão" in c.value for c in at.caption)


def add_last_reading(path: Path, device: str, hours_ago: float, **values) -> None:
    """Uma única leitura de `device`, de `hours_ago` horas atrás, com os valores dados."""
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).replace(second=0, microsecond=0)
    conn = db.connect(str(path))
    db.insert_batch(conn, device, [{"device_id": device, "boot_id": 1, "seq": 0, "uptime_s": 0, "schema_version": "1",
                                    "quality": "ok", "ts_sensor": db.iso(ts), "ts_received": db.iso(ts),
                                    **{**synthetic(ts, {}), **values}}], ts)
    conn.close()


def last_reading_blocks(at) -> list[str]:
    """Os HTMLs da última leitura de cada nó sem dados."""
    return [h.proto.body for h in at.get("html") if 'class="aq-last"' in h.proto.body]


def test_no_sem_dados_nao_mostra_a_ultima_leitura_como_se_fosse_atual(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_last_reading(app_env, "no-02", hours_ago=27, pm25=0.0, pm10=0.0, rssi=-53)  # o nó parou com a leitura em zero
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception

    pm25 = [m for m in at.metric if m.label == "PM2,5"]
    assert pm25[1].value == "—"                  # no-02: nem 0,0 µg/m³ nem a faixa "Boa"
    assert not pm25[1].delta
    assert len(at.metric) == 5                   # os 4 do no-01 e só o PM2,5 do no-02
    assert any("sem dados" in c.value for c in at.caption)

    last = at.expander[0]                        # a última leitura segue acessível, dita como histórico
    assert last.label == "Última leitura recebida"
    assert len(last.get("html")) == 1 and len(last_reading_blocks(at)) == 1      # no-01 está em operação e não tem
    block = last_reading_blocks(at)[0]
    assert "Leitura histórica; não representa a condição atual" in block
    assert re.search(r'PM2,5 \(µg/m³\)</span><span class="aq-last-value">0,0<', block)       # os valores em grade
    assert "Sinal Wi-Fi na leitura: -53 dBm" in block                                           # o sinal é o da leitura
    assert len([c for c in at.caption if c.value.startswith("Sinal Wi-Fi")]) == 1   # o do no-01; o do no-02 não é atual


def test_cartao_sem_dados_esconde_o_pm25_vazio_enquanto_a_ultima_leitura_esta_aberta(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_last_reading(app_env, "no-02", hours_ago=27)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert at.metric[-1].label == "PM2,5" and at.metric[-1].value == "—"       # fechado, o "—" segue dizendo que não há leitura
    # Aberto, o histórico ocupa o lugar do "—", que ficaria repetido sobre os valores. O expansor é um elemento details
    # que só perde o atributo `open` quando termina de fechar, mas marca o conteúdo como `inert` assim que começa:
    # a regra olha o conteúdo ainda ativo, e o bloco volta junto com o início do fechamento, não depois dele.
    hidden = re.search(r"st-key-node-'\]:has\(details\[open\] \[data-testid='stExpanderDetails'\]:not\(\[inert\]\)\)"
                       r"[^{]*st-key-hero-empty-[^{]*\{([^}]*)\}", page_style(at))
    assert hidden, "falta a regra que esconde o PM2,5 vazio com o histórico aberto"
    assert "grid-template-rows: 0fr" in hidden.group(1) and "opacity: 0" in hidden.group(1)      # encolhe e some


def test_pm25_vazio_encolhe_e_volta_com_transicao_em_vez_de_cortar(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_last_reading(app_env, "no-02", hours_ago=27)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    css = page_style(at)
    # O bloco anima a altura (pela fileira da grade, de 1fr a 0fr) e a opacidade nos dois sentidos; sem transição, ele
    # aparecia de uma vez quando o expansor terminava de encolher.
    base = re.search(r"stLayoutWrapper'\]:has\(> \[class\*='st-key-hero-empty-'\]\) \{([^}]*)\}", css)
    assert base, "falta a regra-base do bloco do PM2,5 vazio"
    assert "grid-template-rows: 1fr" in base.group(1)
    assert re.search(r"transition:[^;}]*grid-template-rows[^;}]*opacity", base.group(1))
    # Escondido, o bloco ainda deixaria o espaço entre blocos do cartão: a margem negativa o desconta.
    hidden = re.search(r"stExpanderDetails'\]:not\(\[inert\]\)\)[^{]*\{([^}]*)\}", css).group(1)
    assert "margin-bottom: calc(-1 * var(--aq-gap))" in hidden
    assert "--aq-gap: 1rem" in css and "--aq-gap: .75rem" in wide_screen_rules(at)    # o mesmo espaço do cartão
    assert "prefers-reduced-motion: reduce" in css                                   # sem movimento para quem pede


def test_ultima_leitura_marcada_como_implausivel_diz_isso_dentro_do_expansor(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_last_reading(app_env, "no-02", hours_ago=27, quality="umid_fora_faixa", humidity=120.0)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    last = at.expander[0]
    assert any("implausível (umid_fora_faixa)" in c.value for c in last.caption)


def test_no_em_operacao_continua_com_todos_os_indicadores_e_sem_expansor(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert len(at.metric) == 4
    assert "Última leitura recebida" not in [e.label for e in at.expander]       # o cartão não tem expansor próprio


def aq_scales(at) -> list[str]:
    """Os HTMLs das escalas de faixas que a página desenhou, um por nó com leitura atual."""
    return [h.proto.body for h in at.get("html") if 'class="aq-scale"' in h.proto.body]


def test_cartao_do_no_em_operacao_mostra_a_escala_das_faixas_com_a_leitura_por_extenso(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    scales = aq_scales(at)
    assert len(scales) == 1
    assert re.search(r'aria-label="PM2,5 de \d+,\d µg/m³, na faixa (Boa|Moderada|Ruim|Muito ruim|Péssima)"', scales[0])


def test_no_sem_dados_nao_mostra_a_escala_das_faixas(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_last_reading(app_env, "no-02", hours_ago=27, pm25=0.0, pm10=0.0)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert len(aq_scales(at)) == 1                 # só o no-01: o zero do no-02 não vira uma leitura na escala


def test_todo_grafico_tem_descricao_para_o_leitor_de_tela(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_dead_hours(app_env, "no-01", [10])        # com horas fora, a série horária também desenha a faixa
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    descriptions = [json.loads(c.proto.spec).get("description") for c in at.get("vega_lite_chart")]
    assert len(descriptions) == 5 and all(descriptions), descriptions     # 6 h, PM2,5, umidade, faixa e previsão
    assert any(d.startswith("Gráfico de linhas") and "PM2,5" in d and "no-01" in d for d in descriptions)
    assert any(d.startswith("Faixa das horas sem média") for d in descriptions)
    assert any("observado" in d.lower() and "persistência" in d.lower() for d in descriptions)


def test_cartao_do_no_poe_o_sinal_wifi_numa_linha_a_parte(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert [m.label for m in at.metric] == ["PM2,5", "PM10 (µg/m³)", "Temperatura", "Umidade"]
    wifi = [c.value for c in at.caption if c.value.startswith("Sinal Wi-Fi")]
    assert len(wifi) == 1 and re.fullmatch(r"Sinal Wi-Fi: -?\d+ dBm", wifi[0])


def test_numeros_do_painel_usam_virgula_decimal(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_last_reading(app_env, "no-02", hours_ago=27)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    values = [m.value for m in at.metric if m.value != "—"]
    assert values and all("." not in v and "," in v for v in values), values
    stale = [c.value for c in at.caption if "sem dados" in c.value]
    assert len(stale) == 1 and re.search(r"último envio há \d+,\d h", stale[0]), stale


def control_labels(el) -> list[str]:
    """Os rótulos dos controles de um elemento da aba, na ordem em que aparecem, dentro de colunas ou não."""
    if el.type in ("multiselect", "button_group", "checkbox", "download_button", "date_input"):
        return [el.label]
    return [label for child in getattr(el, "children", {}).values() for label in control_labels(child)]


def series_rows(at) -> list[list[str]]:
    """Os rótulos dos controles do topo da aba Séries, uma lista por linha."""
    rows = []
    for key in sorted(at.tabs[1].children):
        el = at.tabs[1].children[key]
        if el.type != "flex_container":
            break                                   # o primeiro aviso ou gráfico encerra os controles
        rows.append(control_labels(el))
    return rows


def test_filtros_da_aba_series_ficam_em_duas_linhas(app_env):
    populate(app_env, hours=3)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    rows = series_rows(at)
    assert rows[0] == ["Sensores", "Variáveis"]                                 # quem e o quê, lado a lado
    assert rows[1][:3] == ["Período", "Resolução", "Ocultar leituras marcadas"]   # o recorte dos dados, em outra linha
    assert len(rows) == 2


def test_segunda_linha_de_filtros_quebra_em_vez_de_cortar_os_controles(app_env):
    populate(app_env, hours=3)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    row = at.tabs[1].children[sorted(at.tabs[1].children)[1]]
    # Cada controle ocupa o que o seu conteúdo pede e, se a linha não couber, o último desce: com colunas de largura
    # fixa, o botão "1 minuto" e o rótulo do filtro apareciam cortados numa janela de 1024 px.
    assert "direction: HORIZONTAL" in str(row.proto) and "wrap: true" in str(row.proto)
    assert not any(child.type == "column" for child in row.children.values())      # os controles, sem colunas de largura fixa


def test_exportacao_fica_na_linha_dos_filtros_e_nao_depois_dos_graficos(app_env):
    populate(app_env, hours=3)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert series_rows(at)[1][-1] == "Exportar CSV"                  # perto dos filtros que definem o que se exporta
    assert len(at.get("download_button")) == 1                       # e só ali: o botão do fim da página saiu


def test_sem_dados_para_mostrar_nao_ha_o_que_exportar(app_env):
    populate(app_env, hours=3)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    at.multiselect[0].set_value([]).run()                            # nenhum sensor escolhido
    assert not at.exception, at.exception
    assert len(at.get("download_button")) == 0


def test_resolucao_vira_botoes_e_sem_escolha_fica_a_media_horaria(app_env):
    populate(app_env, hours=3)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    resolution = at.segmented_control[1]
    assert resolution.label == "Resolução" and list(resolution.options) == ["Média horária", "1 minuto"]
    assert resolution.value == "Média horária" and len(at.radio) == 0
    resolution.set_value(None).run()                                     # os botões deixam desmarcar
    assert not at.exception, at.exception
    assert any(c.value.startswith("Horas sem média") or "minutos de leitura" in c.value for c in at.caption)


def test_filtro_das_leituras_marcadas_tem_nome_curto_e_explica_no_balao(app_env):
    populate(app_env, hours=3)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    only_ok = at.checkbox[0]
    assert only_ok.label == "Ocultar leituras marcadas" and only_ok.value is True
    assert "implausíveis" in only_ok.help                                 # o motivo da marca fica no balão


def test_periodo_tem_atalhos_e_so_o_personalizado_pede_datas(app_env):
    populate(app_env, hours=3)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    period = at.segmented_control[0]
    assert period.label == "Período" and list(period.options) == ["7 dias", "30 dias", "Personalizado"]
    assert period.value == "7 dias" and len(at.date_input) == 0
    period.set_value("Personalizado").run()
    assert not at.exception, at.exception
    assert len(at.date_input) == 1


def test_30_dias_em_um_minuto_avisa_do_limite(app_env):
    populate(app_env, hours=3)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    at.segmented_control[0].set_value("30 dias").run()
    at.segmented_control[1].set_value("1 minuto").run()
    assert not at.exception, at.exception
    assert any("até 7 dias" in i.value for i in at.info)


def test_serie_horaria_conta_as_horas_sem_media_por_causa(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_dead_hours(app_env, "no-01", [10])
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    note = [c.value for c in at.caption if c.value.startswith("Horas sem média")]
    assert len(note) == 1
    assert "1 suspeita" in note[0] and re.search(r"\d+ sem leituras", note[0])   # as causas com zero hora não entram
    assert len(at.get("vega_lite_chart")) == 5       # 6 h, PM2,5, umidade, faixa das horas sem média e previsão


def test_serie_horaria_mostra_o_no_que_parou_como_sem_leituras_ate_agora(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_last_reading(app_env, "no-02", hours_ago=27)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    note = next(c.value for c in at.caption if c.value.startswith("Horas sem média"))
    assert int(re.search(r"(\d+) sem leituras", note).group(1)) >= 20     # as horas desde que o no-02 parou


def test_resolucao_de_um_minuto_nao_mostra_a_faixa_das_horas_sem_media(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_dead_hours(app_env, "no-01", [10])
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    at.segmented_control[1].set_value("1 minuto").run()
    assert not at.exception, at.exception
    assert not any(c.value.startswith("Horas sem média") for c in at.caption)


def add_dead_hours(path: Path, device: str, hours_ago: list[int]) -> None:
    """Uma hora cheia de leituras com PM1, PM2,5 e PM10 em zero, para cada `hours_ago` (horas antes da hora atual)."""
    top = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    conn = db.connect(str(path))
    for k in hours_ago:
        start = top - timedelta(hours=k)
        dead = {**synthetic(start, {}), "pm25": 0.0, "pm1": 0.0, "pm10": 0.0}
        db.insert_batch(conn, device, [{"device_id": device, "boot_id": 9, "seq": k * 60 + m, "uptime_s": 0,
                                        "schema_version": "1", "quality": "ok",
                                        "ts_sensor": db.iso(start + timedelta(minutes=m)),
                                        "ts_received": db.iso(start + timedelta(minutes=m)), **dead}
                                       for m in range(60)], start)
    conn.close()


HOURS_DETAILS = "Critérios e detalhamento por sensor"


def hours_details(at) -> str:
    """O texto do expansor único da série horária, com a regra das horas, o detalhe por sensor e o critério das suspeitas."""
    boxes = [e for e in at.expander if e.label == HOURS_DETAILS]
    assert len(boxes) == 1, [e.label for e in at.expander]
    return " ".join(c.value for c in boxes[0].caption)


def visible_captions(at) -> list[str]:
    """Os avisos que aparecem sem abrir nenhum expansor."""
    inside = {c.value for e in at.expander for c in e.caption}
    return [c.value for c in at.caption if c.value not in inside]


def test_serie_horaria_diz_as_horas_sem_media_uma_vez_e_leva_o_resto_num_expansor_so(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_dead_hours(app_env, "no-01", [10])
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    visible = visible_captions(at)
    summary = [v for v in visible if v.startswith("Horas sem média")]
    assert len(summary) == 1 and "1 suspeita" in summary[0]
    assert [v for v in visible if "suspeita" in v] == summary          # a contagem de suspeitas não se repete
    assert not any("ficou de fora" in v or "ficaram de fora" in v for v in visible)
    assert not any("minutos de leitura" in v for v in visible)         # a regra dos 45 minutos vai para o expansor


def test_expansor_da_serie_horaria_traz_a_regra_das_horas_e_o_criterio_das_suspeitas(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_dead_hours(app_env, "no-01", [10])
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    text = hours_details(at)
    assert "45 minutos de leitura (75%)" in text                                        # a regra das médias horárias
    assert "25%" in text and "0,5 µg/m³" in text and "1,0 µg/m³" in text               # a regra das suspeitas
    assert "falha do sensor" in text and "ar muito limpo" in text and "CETESB" in text  # a causa não está decidida
    assert not any("o que o ar não faz" in c.value for c in at.caption)


def test_expansor_da_serie_horaria_detalha_as_horas_sem_media_por_sensor(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1), ("no-02", 1)))
    add_dead_hours(app_env, "no-01", [10])
    add_dead_hours(app_env, "no-02", [12, 11])
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    text = hours_details(at)
    assert re.search(r"no-01:\*\* [^-]*1 suspeita", text)             # cada sensor, a sua contagem
    assert re.search(r"no-02:\*\* [^-]*2 suspeitas", text)
    summary = next(v for v in visible_captions(at) if v.startswith("Horas sem média"))
    assert "3 suspeitas" in summary and "soma dos sensores" in summary    # as contagens juntam horas de sensores diferentes


def test_detalhe_por_sensor_so_chama_de_suspeita_o_no_que_tem_horas_suspeitas(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1), ("no-02", 1)))
    add_dead_hours(app_env, "no-02", [10])
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    lines = {m.group(1): m.group(2) for m in re.finditer(r"(no-0\d):\*\* ([^-]*)", hours_details(at))}
    assert "suspeita" in lines["no-02"] and "suspeita" not in lines["no-01"]


def trend_head(at) -> str:
    """O HTML da linha acima do gráfico de 6 horas, com o período, a legenda e os avisos dos nós calados."""
    return next(h.proto.body for h in at.get("html") if 'class="aq-trend-head"' in h.proto.body)


def test_grafico_de_seis_horas_tem_titulo_curto_e_uma_linha_so_com_periodo_e_legenda(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert "#### PM2,5 · últimas 6 horas" in [m.value for m in at.markdown]
    head = trend_head(at)
    assert re.search(r"\d{2}(/\d{2}|–\d{2}/\d{2}| a \d{2}/\d{2}) · µg/m³", head)    # o período e a unidade
    assert "no-01" in head and "background:#22b8cf" in head                            # a legenda, com a cor do nó
    assert "sem leituras" not in head


def chart_heads(at) -> list[str]:
    """Os HTMLs da linha acima de cada gráfico de linhas, na ordem da página: o de 6 horas e depois os da aba Séries."""
    return [h.proto.body for h in at.get("html") if 'class="aq-trend-head"' in h.proto.body]


def series_flow(at) -> list[tuple[str, str]]:
    """O que a aba Séries mostra depois dos filtros, em ordem: avisos, a linha de cada gráfico e os gráficos."""
    flow = []
    for key in sorted(at.tabs[1].children):
        el = at.tabs[1].children[key]
        if el.type == "caption":
            flow.append(("aviso", el.value))
        elif el.type == "html" and 'class="aq-trend-head"' in el.proto.body:
            flow.append(("linha", re.search(r'aq-label[^>]*>([^<]*)<', el.proto.body).group(1)))
        elif el.type == "vega_lite_chart":
            flow.append(("grafico", json.loads(el.proto.spec)["description"]))
    return flow


STRIP_TITLE = "Qualidade da coleta por hora"


def test_faixa_das_horas_sem_media_tem_titulo_legenda_das_causas_e_diz_o_que_e_o_branco(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_dead_hours(app_env, "no-01", [10])
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    flow = series_flow(at)
    title = flow.index(("linha", STRIP_TITLE))
    assert flow[title + 1][0] == "grafico" and flow[title + 1][1].startswith("Faixa das horas sem média")  # colado nela
    head = next(h for h in chart_heads(at) if STRIP_TITLE in h)
    assert 'class="aq-label aq-title"' in head                                       # com o destaque dos outros títulos
    assert "</i>sem leituras</span>" in head and "background:#8b93a1" in head       # cada causa, com a cor da faixa
    assert "</i>suspeita</span>" in head and "background:#e2b53b" in head
    assert "em branco: hora válida</span>" in head                                   # e o que o espaço vazio quer dizer


def test_faixa_das_horas_sem_media_nao_repete_a_legenda_dentro_do_grafico(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_dead_hours(app_env, "no-01", [10])
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    specs = [json.loads(c.proto.spec) for c in at.get("vega_lite_chart")]
    strip = next(s for s in specs if s["description"].startswith("Faixa das horas sem média"))
    assert strip["encoding"]["color"].get("legend", "padrão") is None             # a legenda vai na linha de cima


def test_sem_a_faixa_das_horas_sem_media_nao_ha_titulo_dela(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_dead_hours(app_env, "no-01", [10])
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    at.segmented_control[1].set_value("1 minuto").run()                            # a faixa só existe na média horária
    assert not at.exception, at.exception
    assert ("linha", STRIP_TITLE) not in series_flow(at)


def test_expansor_diz_que_o_branco_da_faixa_tambem_e_antes_da_primeira_leitura_e_a_hora_em_andamento(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_dead_hours(app_env, "no-01", [10])
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    text = hours_details(at)
    # A faixa só pinta as horas sem média, e o dashboard só conta as horas entre a primeira e a última leitura de cada
    # sensor: o branco nem sempre é hora válida, e a legenda curta não pode prometer isso sem a exceção por perto.
    assert "em branco" in text and "antes da primeira leitura" in text and "hora em andamento" in text


def test_explicacao_da_umidade_fica_logo_abaixo_do_grafico_de_umidade(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    at.multiselect[1].set_value(["humidity", "pm25"]).run()           # a umidade primeiro: o fim da página não é dela
    assert not at.exception, at.exception
    flow = series_flow(at)
    chart = next(i for i, (kind, text) in enumerate(flow) if kind == "grafico" and "Umidade" in text)
    assert flow[chart + 1][0] == "aviso" and flow[chart + 1][1].startswith("Registros com umidade acima de 75%")
    assert sum(text.startswith("Registros com umidade") for kind, text in flow if kind == "aviso") == 1


def test_sem_o_grafico_de_umidade_a_explicacao_da_umidade_nao_aparece(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    at.multiselect[1].set_value(["pm25"]).run()
    assert not at.exception, at.exception
    assert not any(text.startswith("Registros com umidade") for kind, text in series_flow(at))


def test_linha_de_75_por_cento_do_grafico_de_umidade_tem_rotulo(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    spec = next(json.loads(c.proto.spec) for c in at.get("vega_lite_chart") if "Umidade" in json.loads(c.proto.spec)["description"])
    labels = [layer for layer in spec["layer"] if layer["mark"]["type"] == "text"]
    assert len(labels) == 1 and labels[0]["encoding"]["text"] == {"value": "75%"}          # o rótulo da linha tracejada


def test_cada_grafico_da_aba_series_tem_a_variavel_e_a_legenda_numa_linha(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1), ("no-02", 1)))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    heads = chart_heads(at)
    assert len(heads) == 4                          # o de 6 horas, PM2,5, a faixa das horas sem média e a umidade
    variables = [head for head in heads[1:] if STRIP_TITLE not in head]
    assert "PM2,5 (µg/m³)" in variables[0] and "Umidade relativa (%)" in variables[1]
    for head in variables:
        assert "background:#22b8cf" in head and "background:#e0529c" in head      # cada sensor, com a cor da sua linha
        assert "</i>no-01</span>" in head and "</i>no-02</span>" in head


def test_titulo_de_cada_grafico_da_aba_series_tem_destaque_e_a_nota_do_grafico_de_seis_horas_nao(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1), ("no-02", 1)))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    heads = chart_heads(at)
    assert "aq-title" not in heads[0]                    # o 6 horas já tem o seu #### em cima: o período fica como nota
    assert all('class="aq-label aq-title"' in head for head in heads[1:])
    css = page_style(at)
    assert rem_of(css, ".aq-label.aq-title", "font-size") == 1               # 16 px, como o texto do corpo da página
    rule = re.search(r"[.]aq-label[.]aq-title\s*[{]([^}]*)[}]", css).group(1)
    assert "font-weight: 600" in rule and "opacity: 1" in rule             # seminegrito e sem o apagado das notas


def test_graficos_da_aba_series_nao_repetem_titulo_e_legenda_dentro_do_grafico(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1), ("no-02", 1)))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    specs = [json.loads(c.proto.spec) for c in at.get("vega_lite_chart")]
    lines = [s for s in specs if s["description"].startswith("Gráfico de linhas") and "por sensor" in s["description"]][1:]
    assert len(lines) == 2
    for spec in lines:
        assert "title" not in spec                                  # o nome da variável vai na linha de cima
        colors = [layer["encoding"]["color"] for layer in spec.get("layer", [spec]) if "color" in layer.get("encoding", {})]
        assert colors and all(c.get("legend") is None for c in colors)          # e a legenda também
        assert spec["height"] <= 250                                 # sem o cabeçalho, a área das linhas segue a mesma


def test_grafico_de_seis_horas_nao_repete_titulo_e_legenda_dentro_do_grafico(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    spec = json.loads(at.get("vega_lite_chart")[0].proto.spec)
    assert "title" not in spec                       # o título e o período já vêm acima do gráfico
    colors = [layer["encoding"]["color"] for layer in spec.get("layer", [spec]) if "color" in layer.get("encoding", {})]
    assert colors and all(c.get("legend") is None for c in colors)     # e a legenda também


def status_chart(at) -> dict:
    """A especificação do gráfico de 6 horas, o primeiro da página."""
    return json.loads(at.get("vega_lite_chart")[0].proto.spec)


def test_eixo_do_grafico_de_seis_horas_marca_de_meia_em_meia_hora(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    spec = status_chart(at)
    axes = [layer["encoding"]["x"]["axis"] for layer in spec.get("layer", [spec]) if "x" in layer.get("encoding", {})]
    # Doze marcas em 6 horas dão uma a cada 30 minutos (eram 24, de 15 em 15). Um intervalo explícito no eixo
    # (`{"interval": "minute", "step": 30}`) deixa o gráfico em branco no Streamlit, por isso a contagem é numérica.
    assert any(axis.get("tickCount") == 12 for axis in axes)


def test_linha_do_grafico_de_seis_horas_e_fina_e_so_mostra_o_ponto_sob_o_mouse(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    spec = status_chart(at)
    line = next(layer["mark"] for layer in spec["layer"] if layer["mark"]["type"] == "line")
    assert not line.get("point")                                 # sem um ponto por leitura (eram 360)
    assert 1.75 <= line["strokeWidth"] <= 2                      # fina, mas não a ponto de sumir
    selections = [p["select"] for p in spec["params"]]           # o Altair junta as seleções no topo da especificação
    assert any(s["type"] == "point" and s["nearest"] and s["on"] == "pointerover" for s in selections)  # o ponto sob o mouse


def test_leitura_isolada_no_grafico_de_seis_horas_continua_com_o_seu_ponto(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_last_reading(app_env, "no-02", hours_ago=0.02)           # uma leitura só, sem vizinhas para ligar a uma linha
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    chart = at.get("vega_lite_chart")[0].proto            # o Streamlit manda os dados à parte da especificação
    rows = pa.ipc.open_stream(chart.datasets[0].data.data).read_all().to_pandas()
    assert set(rows.loc[rows["isolado"], "device_id"]) == {"no-02"}   # as 180 leituras seguidas do no-01 formam uma linha
    layers = json.loads(chart.spec)["layer"]
    assert any("isolado" in json.dumps(layer.get("transform", [])) for layer in layers)    # e só as isoladas têm ponto fixo


def test_cabecalho_do_grafico_explica_o_no_que_nao_enviou_nada(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_last_reading(app_env, "no-02", hours_ago=27)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    head = trend_head(at)
    assert "no-02 · sem leituras neste período" in head and "no-01 · sem" not in head
    assert not any("sem leituras nas últimas" in c.value for c in at.caption)   # o aviso saiu de baixo do gráfico


def test_cabecalho_do_grafico_nao_avisa_quando_todos_os_nos_enviaram(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1), ("no-02", 1)))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    head = trend_head(at)
    assert "sem leituras" not in head and "no-01" in head and "no-02" in head


def test_cabecalho_do_grafico_avisa_quando_nenhum_no_enviou(app_env):
    conn = db.connect(str(app_env))
    db.init_db(conn)
    conn.close()
    add_last_reading(app_env, "no-01", hours_ago=30)
    add_last_reading(app_env, "no-02", hours_ago=27)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert "no-01, no-02 · sem leituras neste período" in trend_head(at)


def test_sem_horas_suspeitas_a_serie_horaria_nao_menciona_o_assunto(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert not any("suspeita" in c.value for c in at.caption)


def test_mostra_a_versao_do_firmware_quando_o_no_informa(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1), ("no-02", 1)))
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    conn = db.connect(str(app_env))
    db.insert_batch(conn, "no-01", [{"device_id": "no-01", "boot_id": 1, "seq": 3 * 60, "ts_sensor": db.iso(now),
                                     "ts_received": db.iso(now), "uptime_s": 3 * 3600, "schema_version": "1",
                                     "quality": "ok", **synthetic(now, {})}], now, firmware="build Oct 26 2026")
    conn.close()
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    firmware = [c.value for c in at.caption if "Firmware" in c.value]
    assert firmware == ["Firmware: build Oct 26 2026"]               # o no-02 não informa: nada é mostrado


def test_avisa_quando_a_ultima_leitura_foi_marcada(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    conn = db.connect(str(app_env))  # a tabela é imutável: a leitura marcada entra como a mais recente
    db.insert_batch(conn, "no-01", [{"device_id": "no-01", "boot_id": 1, "seq": 3 * 60, "ts_sensor": db.iso(now),
                                     "ts_received": db.iso(now), "uptime_s": 3 * 3600, "schema_version": "1",
                                     "quality": "umid_fora_faixa", **synthetic(now, {}), "humidity": 120.0}], now)
    conn.close()
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert any("implausível (umid_fora_faixa)" in c.value for c in at.caption)


def test_troca_para_resolucao_de_um_minuto(app_env):
    populate(app_env, hours=3)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    at.segmented_control[1].set_value("1 minuto").run()
    assert not at.exception, at.exception


def test_no_em_operacao_com_leitura_zerada_fica_sem_faixa_e_diz_por_que(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_last_reading(app_env, "no-02", hours_ago=0.02, pm1=0.0, pm25=0.0, pm10=0.0)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception

    pm25 = [m for m in at.metric if m.label == "PM2,5"]
    assert pm25[1].value == "0,0"                # o valor segue visível: é o que o nó enviou
    assert not pm25[1].delta                     # mas sem o selo "Boa", que um sensor parado em zero não merece
    assert len(aq_scales(at)) == 1               # a escala é só do no-01
    notes = [c.value for c in at.caption if "Leitura zerada" in c.value]
    assert len(notes) == 1
    assert "PM1, PM2,5 e PM10" in notes[0] and "pode não estar vendo partículas" in notes[0]
    assert "sem faixa" in notes[0]


def test_leitura_com_particulas_nao_traz_o_aviso_de_leitura_zerada(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert not [c for c in at.caption if "zerada" in c.value]
    assert [m for m in at.metric if m.label == "PM2,5"][0].delta


def test_pm10_leva_a_unidade_no_rotulo_para_o_valor_caber_na_coluna_estreita(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    pm10 = next(m for m in at.metric if m.label.startswith("PM10"))
    assert re.fullmatch(r"\d+,\d", pm10.value), pm10.value   # "50,9 µg/m³" ficava cortado num cartão de meia tela


@pytest.mark.parametrize("values, named", [
    ({"pm1": None, "pm25": 0.0, "pm10": 0.0}, "(PM2,5 e PM10 em 0,0)"),
    ({"pm1": 0.0, "pm25": 0.0, "pm10": None}, "(PM1 e PM2,5 em 0,0)"),
])
def test_nota_da_leitura_zerada_cita_so_as_particulas_que_o_no_enviou(app_env, values, named):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_last_reading(app_env, "no-02", hours_ago=0.02, **values)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    notes = [c.value for c in at.caption if "Leitura zerada" in c.value]
    assert len(notes) == 1 and notes[0].startswith(f"Leitura zerada {named}:"), notes


def shown(table):
    """O que a tabela escreve nas células: os valores formatados pelo Styler, ou os próprios valores sem ele."""
    display = table.proto.arrow_data.styler.display_values
    if not display:
        return table.value.astype(str)
    return pa.ipc.open_stream(display).read_all().to_pandas()


def has_decimal_point(text) -> bool:
    return bool(text.apply(lambda col: col.str.contains(".", regex=False)).any().any())


def test_tabela_de_saude_escreve_os_numeros_com_virgula_e_mantem_a_barra(app_env):
    populate(app_env)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    table = at.dataframe[0]
    assert list(table.value.columns[:3]) == ["Sensor", "Completude", "%"]  # a barra e o número ao lado dela
    text = shown(table)
    assert text["%"].str.fullmatch(r"\d+,\d\d%").all(), list(text["%"])
    assert not has_decimal_point(text), text


def test_tabela_de_saude_escreve_a_maior_lacuna_em_horas_e_minutos(app_env):
    populate(app_env)                                            # o no-02 ficou uma hora sem dados
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert "Maior lacuna" in at.dataframe[0].value.columns and "Maior lacuna (min)" not in at.dataframe[0].value.columns
    text = shown(at.dataframe[0]).set_index("Sensor")
    assert text.loc["no-02", "Maior lacuna"] == "1 h"
    assert re.fullmatch(r"\d+ min", text.loc["no-01", "Maior lacuna"]), text.loc["no-01", "Maior lacuna"]


def test_no_que_nao_mandou_nada_em_24_horas_tem_a_maior_lacuna_de_24_h(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_last_reading(app_env, "no-02", hours_ago=27)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    text = shown(at.dataframe[0]).set_index("Sensor")
    assert text.loc["no-02", "Maior lacuna"] == "24 h"           # em vez de 1440 (min)


def test_explicacao_da_tabela_de_saude_vai_num_expansor_e_nao_afirma_a_causa(app_env):
    populate(app_env)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    box = [e for e in at.expander if e.label == "Como interpretar os indicadores"]
    assert len(box) == 1
    text = " ".join(c.value for c in box[0].caption)
    assert "lacunas de sequência" in text                       # o que são as mensagens perdidas
    assert "sugerem falha do sensor" in text and "não confirma a causa" in text    # uma hipótese, não uma causa
    assert "indicam falha do sensor" not in text
    inside = {c.value for c in box[0].caption}
    assert not any("lacunas de sequência" in c.value for c in at.caption if c.value not in inside)   # nada solto sob a tabela


def test_explicacao_da_tabela_de_saude_define_cada_indicador_da_tabela(app_env):
    populate(app_env)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    box = next(e for e in at.expander if e.label == "Como interpretar os indicadores")
    text = " ".join(c.value for c in box.caption)
    indicators = [c for c in at.dataframe[0].value.columns if c not in ("Sensor", "%")]   # "%" repete a completude
    assert len(indicators) == 6
    for name in indicators:
        assert f"**{name}:**" in text, f"a tabela tem a coluna {name} e a explicação não a define"
    assert "minutos esperados" in text and "implausíveis" in text        # o que são a completude e as leituras marcadas


def test_tabela_de_previsao_escreve_os_numeros_com_virgula(app_env):
    populate(app_env)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    text = shown(at.dataframe[1])
    for column in ("MAE (µg/m³)", "RMSE (µg/m³)", "Skill score"):
        assert text[column].str.fullmatch(r"-?\d+,\d\d").all(), (column, list(text[column]))
    assert not has_decimal_point(text), text


def page_style(at) -> str:
    return next(h.proto.body for h in at.get("html") if "stMainBlockContainer" in h.proto.body)


def wide_screen_rules(at) -> str:
    """As regras que valem a partir de 640 px, a largura em que o Streamlit deixa de empilhar as colunas."""
    block = re.search(r"@media \(min-width: 640px\) \{(.*?)\n\}", page_style(at), re.S)
    assert block, "faltam as regras do cabeçalho para telas largas"
    return block.group(1)


def rem_of(rules: str, selector: str, prop: str) -> float:
    match = re.search(rf"{re.escape(selector)}\s*\{{[^}}]*?{prop}:\s*([\d.]+)rem", rules)
    assert match, f"{selector} sem {prop} em rem"
    return float(match.group(1))


def test_estilo_da_pagina_nao_tem_sinal_de_menor_dentro_do_css(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    css = re.fullmatch(r"<style>(.*)</style>", page_style(at), re.S)
    assert css, "o estilo precisa ser um bloco <style> só"
    # O sanitizador do st.html joga fora o <style> inteiro se achar um "<" dentro dele, até num comentário: a página
    # fica sem nenhum dos estilos, e nenhum teste que leia o texto do CSS percebe.
    assert "<" not in css.group(1)


def test_cabecalho_em_tela_larga_gasta_menos_altura(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    rules = wide_screen_rules(at)
    assert 1.5 <= rem_of(rules, "[data-testid='stMainBlockContainer']", "padding-top") <= 2.0   # 24 a 32 px (era 56)
    assert 1.625 <= rem_of(rules, "h1", "font-size") <= 1.75                                   # 26 a 28 px (era 44)
    assert rem_of(rules, "h1", "padding-bottom") <= 0.5                                         # o título junto das abas
    assert rem_of(rules, "[role='tabpanel']", "padding-top") <= 0.5                             # e as abas, do conteúdo
    # A barra do Streamlit fica por cima do conteúdo e tem fundo sólido: com a margem menor ela esconderia o título.
    assert re.search(r"\[data-testid='stHeader'\]\s*\{[^}]*background:\s*transparent", rules)


def test_cabecalho_no_celular_segue_como_esta(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    # Fora da regra de tela larga a margem de cima fica em 3,5rem: no celular a barra do Streamlit cobriria uma menor.
    assert "padding-top: 3.5rem" in page_style(at).split("@media")[0]


def set_location(path: Path, device: str, location: str) -> None:
    conn = db.connect(str(path))
    db.set_location(conn, device, location)
    conn.close()


def test_cartao_junta_nome_e_local_no_titulo(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1), ("no-02", 2)))
    set_location(app_env, "no-01", "Osasco")
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert [s.value for s in at.subheader][:2] == ["no-01 · Osasco", "no-02"]   # sem local, só o nome
    assert "Osasco" not in [c.value for c in at.caption]                          # o local não ganha uma linha só dele


def test_unidade_do_pm25_vai_menor_ao_lado_do_valor(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    pm25 = [m for m in at.metric if m.label == "PM2,5"][0]
    assert re.fullmatch(r"\d+,\d", pm25.value), pm25.value        # o valor é só o número...
    # ...e a unidade é escrita pelo estilo, menor e com peso normal, só onde há uma leitura (não no "—" do nó sem dados).
    unit = re.search(r"st-key-hero-'\]:not\(\[class\*='st-key-hero-empty-'\]\)[^{]*::after\s*\{([^}]*)\}", page_style(at))
    assert unit, "falta a regra que escreve a unidade ao lado do valor"
    assert 'content: " µg/m³"' in unit.group(1) and "font-weight: 400" in unit.group(1)


def test_cartao_do_no_em_tela_larga_tem_blocos_mais_juntos(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    rules = wide_screen_rules(at)
    node = "[data-testid='stVerticalBlock'][class*='st-key-node-']"
    assert rem_of(rules, node, "gap") <= 0.75                                   # 12 px entre os grupos (eram 16)
    assert rem_of(rules, node, "padding") <= 0.75                               # e 12 px de margem interna
    assert rem_of(rules, "[data-testid='stHeading'] h3", "font-size") <= 1.5   # o nome do nó não domina o cartão
    # O selo da faixa fica ao lado do valor, não numa linha só dele: a grade põe o rótulo em cima e os dois embaixo.
    grid = re.search(r"\[data-testid='stMetric'\] > div \{([^}]*)\}", rules)
    assert grid and "display: grid" in grid.group(1), "falta a grade do PM2,5 com o selo da faixa ao lado do valor"
    # A escala junto das métricas. O seletor leva o cartão: a regra-base da escala vem depois no CSS e venceria um empate.
    assert rem_of(rules, "[class*='st-key-hero-'] .aq-scale", "margin-bottom") <= 0.5
    # O Streamlit tira 16 px da altura do título para compensar o espaço que ele mesmo põe embaixo; sem esse espaço, a
    # compensação encurtaria a caixa do título e o texto cairia sobre a linha do estado.
    assert re.search(r"\[data-testid='stMarkdownContainer'\]\s*\{[^}]*margin-bottom:\s*0[;} ]", rules)
