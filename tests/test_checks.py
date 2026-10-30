import datetime as dt

import pytest

from app.checks.dates import encontrar_fechas_con_mes, resolver_fecha, validar_plazo
from app.checks.digits import coinciden, extraer_digitos
from app.checks.numbers import encontrar_montos, parse_numero
from app.checks.text import plegar

LLAMADA = dt.date(2026, 9, 22)  # martes


# ------------------------------------------------------------------ números

@pytest.mark.parametrize("texto, valor", [
    ("un millón doscientos cincuenta mil", 1_250_000),
    ("ochocientos treinta mil", 830_000),
    ("dos millones cuatrocientos mil", 2_400_000),
    ("un millón novecientos ochenta mil", 1_980_000),
    ("un millón quinientos ochenta y cuatro mil", 1_584_000),
    ("un millón ciento cincuenta mil", 1_150_000),
    ("tres millones cien mil", 3_100_000),
    ("cuatrocientos cincuenta mil", 450_000),
    ("novecientos veinte mil", 920_000),
    ("un millón setecientos veinte mil", 1_720_000),
    ("dos millones seiscientos veinte mil", 2_620_000),
    ("setecientos ochenta mil", 780_000),
    ("quinientos cuarenta mil", 540_000),
    ("un millón trescientos noventa mil", 1_390_000),
    ("trescientos diez mil", 310_000),
    ("novecientos sesenta mil", 960_000),
    ("un millón cincuenta mil", 1_050_000),
    ("un millón cuatrocientos setenta mil", 1_470_000),
    ("ochocientos setenta mil", 870_000),
    # bordes
    ("$1.250.000", 1_250_000),
    ("1,250,000", 1_250_000),
    ("1250000", 1_250_000),
    ("2,4 millones", 2_400_000),
    ("1 millón 250 mil", 1_250_000),
    ("mil quinientos", 1_500),
    ("doscientos mil quinientos", 200_500),
    ("veintiún mil", 21_000),
    ("cien mil", 100_000),
    ("ciento un mil", 101_000),
])
def test_parse_numero(texto, valor):
    assert parse_numero(texto) == valor


def test_encontrar_montos_en_contexto():
    texto = ("Su tarjeta presenta un saldo vencido de un millón doscientos cincuenta mil pesos, "
             "con fecha de vencimiento el 15 de septiembre.")
    montos = encontrar_montos(texto)
    assert [m.valor for m in montos] == [1_250_000]
    assert montos[0].texto in texto


def test_montos_no_confunde_dias_horas_ni_porcentajes():
    texto = "Puede tardar 48 horas; si paga el 25 le aplicamos un 20% sobre los cuatro dígitos."
    assert encontrar_montos(texto) == []


def test_monto_en_cifras_y_millones_de_pesos():
    assert [m.valor for m in encontrar_montos("Debe $1.250.000 desde agosto")] == [1_250_000]
    assert [m.valor for m in encontrar_montos("son dos millones de pesos")] == [2_000_000]
    assert [m.valor for m in encontrar_montos("quedan 500 pesos")] == [500]


def test_plegar_conserva_longitud():
    s = "Óscar Julián, ¿cuándo pagará?"
    assert len(plegar(s)) == len(s)
    assert plegar(s) == "oscar julian, ¿cuando pagara?"


# ------------------------------------------------------------------ dígitos

@pytest.mark.parametrize("texto, digitos", [
    ("4821.", "4821"),
    ("48 21", "4821"),
    ("4-8-2-1", "4821"),
    ("A ver... uno, tres, cinco, dos.", "1352"),
    ("cuatro ocho dos uno", "4821"),
    ("cuarenta y ocho, veintiuno", "4821"),
    ("cero siete uno cinco", "0715"),
    ("Sí, claro: 6295", "6295"),
])
def test_extraer_digitos(texto, digitos):
    assert extraer_digitos(texto) == digitos


def test_digitos_transpuestos_no_coinciden():
    assert not coinciden("6295", "6259")
    assert coinciden("6259", "6259")
    assert coinciden("10203046259", "6259")  # dijo el documento completo
    assert not coinciden("625", "6259")


# ------------------------------------------------------------------ fechas

def test_fechas_con_mes():
    fechas = encontrar_fechas_con_mes("con vencimiento el 30 de agosto. Pague el 25/09", LLAMADA)
    assert [f.fecha for f in fechas] == [dt.date(2026, 8, 30), dt.date(2026, 9, 25)]


@pytest.mark.parametrize("texto, fecha, concreta", [
    ("el sábado 26", dt.date(2026, 9, 26), True),
    ("el 4 de octubre", dt.date(2026, 10, 4), True),
    ("lunes 21 de septiembre", dt.date(2026, 9, 21), True),
    ("el lunes 21", dt.date(2026, 9, 21), True),
    ("25/09", dt.date(2026, 9, 25), True),
    ("el 2", dt.date(2026, 10, 2), True),        # día ya pasado hace > 7 días -> mes siguiente
    ("mañana", dt.date(2026, 9, 23), True),
    ("pasado mañana", dt.date(2026, 9, 24), True),
    ("El sábado.", None, False),                   # día sin número: no es concreto
    ("la otra semana", None, False),
    ("veintisiete de septiembre", dt.date(2026, 9, 27), True),
])
def test_resolver_fecha(texto, fecha, concreta):
    r = resolver_fecha(texto, LLAMADA)
    assert r.concreta is concreta
    assert r.fecha == fecha


def test_inconsistencia_dia_semana():
    r = resolver_fecha("el viernes 26 de septiembre", LLAMADA)
    assert r.fecha == dt.date(2026, 9, 26)
    assert r.inconsistencia and "sábado" in r.inconsistencia


def test_fecha_otro_anio():
    r = resolver_fecha("el 3 de enero", dt.date(2026, 12, 30))
    assert r.fecha == dt.date(2027, 1, 3)


@pytest.mark.parametrize("fecha, valida", [
    (dt.date(2026, 9, 22), True),    # mismo día
    (dt.date(2026, 9, 27), True),    # frontera exacta +5 (inclusive)
    (dt.date(2026, 9, 28), False),   # +6
    (dt.date(2026, 9, 21), False),   # anterior a la llamada
    (dt.date(2026, 10, 4), False),   # otro mes, +12
])
def test_validar_plazo(fecha, valida):
    assert validar_plazo(fecha, LLAMADA).valida is valida
