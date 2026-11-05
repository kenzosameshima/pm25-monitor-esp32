"""A ponte entre uma previsão ao vivo e a retroativa da mesma versão, no gráfico da aba de previsão."""

import pandas as pd

RETRO_SUFFIX = "-retro"        # o mesmo sufixo que scripts/forecast_job.py põe na versão retroativa
HOUR = pd.Timedelta(hours=1)


def retro_bridges(long: pd.DataFrame, x: str = "hora_local", color: str = "serie", y: str = "pm25") -> pd.DataFrame:
    """As metades de linha que ligam `<previsor>` e `<previsor>-retro` quando uma hora é seguida, na hora seguinte, pela
    outra série: duas metades por ponte, cada uma na cor da sua série, que se encontram no ponto médio. Horas separadas
    por uma lacuna não são ligadas: a linha não pode dizer que houve previsão onde não houve. Colunas: x, y, color, segmento."""
    columns = [x, y, color, "segmento"]
    names = set(long[color])
    rows = []
    for retro in sorted(n for n in names if n.endswith(RETRO_SUFFIX) and n[:-len(RETRO_SUFFIX)] in names):
        live = retro[:-len(RETRO_SUFFIX)]
        points = long[long[color].isin([live, retro])].drop_duplicates([x, color]).set_index([color, x])[y]
        for (name, hour), value in points.items():
            other = retro if name == live else live
            after = hour + HOUR
            if (other, after) not in points.index:
                continue
            middle = (value + points[(other, after)]) / 2
            half = hour + HOUR / 2
            tag = f"ponte-{live}-{hour:%Y%m%d%H}"
            rows += [{x: hour, y: value, color: name, "segmento": tag + "-a"},
                     {x: half, y: middle, color: name, "segmento": tag + "-a"},
                     {x: half, y: middle, color: other, "segmento": tag + "-b"},
                     {x: after, y: points[(other, after)], color: other, "segmento": tag + "-b"}]
    return pd.DataFrame(rows, columns=columns)
