import pandas as pd

from dashboard.bridges import retro_bridges


def series(**points: dict[int, float]) -> pd.DataFrame:
    return pd.DataFrame([{"hora_local": pd.Timestamp(2026, 11, 3, h), "serie": name, "pm25": v}
                         for name, hours in points.items() for h, v in hours.items()])


def test_consecutive_hours_get_two_halves_meeting_in_the_middle():
    bridges = retro_bridges(series(**{"ridge v0-retro": {2: 10.0}, "ridge v0": {3: 20.0}}))
    assert list(bridges["serie"]) == ["ridge v0-retro", "ridge v0-retro", "ridge v0", "ridge v0"]
    assert list(bridges["pm25"]) == [10.0, 15.0, 15.0, 20.0]
    assert list(bridges["hora_local"].dt.minute) == [0, 30, 30, 0]
    assert bridges["segmento"].nunique() == 2


def test_works_in_both_directions():
    bridges = retro_bridges(series(**{"ridge v0": {2: 10.0}, "ridge v0-retro": {3: 20.0}}))
    assert list(bridges["serie"]) == ["ridge v0", "ridge v0", "ridge v0-retro", "ridge v0-retro"]


def test_a_gap_is_not_bridged():
    assert retro_bridges(series(**{"ridge v0-retro": {2: 10.0}, "ridge v0": {4: 20.0}})).empty


def test_same_series_and_unrelated_series_are_not_bridged():
    assert retro_bridges(series(**{"ridge v0": {2: 1.0, 3: 2.0}, "Persistência": {2: 3.0, 3: 4.0}})).empty
    assert retro_bridges(series(**{"ridge v0-retro": {2: 1.0}, "ridge v1": {3: 2.0}})).empty
