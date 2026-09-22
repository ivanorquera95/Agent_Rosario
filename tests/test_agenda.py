# Funcion pura: arma el texto "cuando" sin tocar BigQuery.
from datetime import date

from agenda.consultar_agenda import texto_cuando


def test_un_solo_dia():
    assert texto_cuando([date(2026, 9, 22)]) == "martes 22"


def test_varios_dias():
    assert texto_cuando([date(2026, 9, 22), date(2026, 10, 31)]) == "del 22/9 al 31/10"