"""Hechos objetivos calculados por código y criterios que se resuelven de forma determinista."""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from app.checks.dates import encontrar_fechas_con_mes
from app.checks.digits import coinciden, extraer_digitos
from app.checks.numbers import encontrar_montos
from app.checks.text import plegar
from app.evidence import cita_turno
from app.rubric import POR_ID
from app.schemas import Cita, Conversacion, ResultadoCriterio, Turno

# ------------------------------------------------------------------ patrones (sobre texto plegado)

RE_LINA = re.compile(r"\blina\b")
RE_EMPRESA = re.compile(r"\bbanco andino\b")
RE_VIRTUAL = re.compile(r"\b(asistente|agente) (virtual|digital)\b")
RE_GRABACION = re.compile(r"\bgraba(da|do|ndo|cion|r|mos)\b")
RE_PIDE_DIGITOS = re.compile(r"\bdigitos\b|\bnumero de (su )?(documento|cedula)\b")
RE_PREGUNTA_IDENTIDAD = re.compile(r"\?|\bhablo con\b|\bes usted\b|\bse encuentra\b")
RE_DEUDA = re.compile(r"\b(saldo|deuda|vencid[oa]s?|vence|vencia|vencimiento|mora|pago pendiente|obligacion)\b")
RE_PRODUCTO_GENERICO = re.compile(r"\bsu (tarjeta|prestamo|credito|obligacion|deuda|cuenta)\b")
RE_VENCIMIENTO = re.compile(r"\b(vencid[oa]s?|vence|vencia|vencio|vencimiento|desde)\b")
RE_PROHIBIDOS = re.compile(
    r"\b(cobro (pre)?juridico|juridic[oa]s?|judicial(es)?|acci(on|ones) legal(es)?|legal(es)?|"
    r"demand(a|as|ar|aremos|arlo|arla)|abogad[oa]s?|embarg\w*|centrales? de riesgo|datacredito|cifin|"
    r"transunion|reportad[oa]s? (a|en|ante)|reporte negativo|juzgado|juez)\b"
)
RE_NO_TITULAR = re.compile(
    r"^\W*no\b|\bno (esta|se encuentra|vive)\b|\b(habla|soy) (la|el|su) (espos|hij|mama|papa|herman|"
    r"novi|compan|amig|vecin)|\bes mi (espos|hij|mama|papa|herman)|\bequivocad|\bse equivoco\b"
)
RE_SI_TITULAR = re.compile(r"^\W*(si|claro|correcto)\b|\bsoy yo\b|\bcon (el|ella)\b|\b(el|ella) habla\b|"
                           r"\bservidor[a]?\b|\ba la orden\b")
RE_CLIENTE_COLGO = re.compile(r"cliente (finalizo|colgo|corto|termino)|se (corto|cayo) la llamada")

_ORACION = re.compile(r"[^.?!¿¡]*[¿¡]?[^.?!]*[.?!]?")


def oracion_en(texto: str, pos: int) -> str:
    """Oración literal del texto que contiene la posición pos (para citas cortas)."""
    inicio = max(texto.rfind(".", 0, pos), texto.rfind("?", 0, pos), texto.rfind("!", 0, pos)) + 1
    fines = [i for i in (texto.find(".", pos), texto.find("?", pos), texto.find("!", pos)) if i != -1]
    fin = min(fines) + 1 if fines else len(texto)
    return texto[inicio:fin].strip()


# ------------------------------------------------------------------ hechos

@dataclass
class Mencion:
    turno: int
    texto: str          # literal
    valor: object = None


@dataclass
class HechosCodigo:
    turnos_agente: list[int]
    ventana_presentacion: list[int]
    lina: Mencion | None = None
    asistente_virtual: Mencion | None = None
    empresa: Mencion | None = None
    grabacion: Mencion | None = None
    confirma_nombre: Mencion | None = None
    pide_digitos: Mencion | None = None
    digitos_cliente: Mencion | None = None        # valor = dígitos dichos
    digitos_coinciden: bool | None = None
    revela_deuda: Mencion | None = None           # primer turno del agente que revela información
    revelaciones: list[Mencion] = field(default_factory=list)
    monto_informado: Mencion | None = None        # valor = int
    fecha_vencimiento_informada: Mencion | None = None  # valor = date | None
    terminos_prohibidos: list[Mencion] = field(default_factory=list)
    es_titular_heuristico: bool | None = None
    respuesta_identidad: Mencion | None = None
    cliente_colgo: bool = False
    ultimo_turno_agente: int | None = None

    def resumen_para_llm(self) -> dict:
        """Hechos ya calculados por código que el LLM recibe como contexto (no los debe re-juzgar)."""
        def m(x: Mencion | None):
            return None if x is None else {"turno": x.turno, "texto": x.texto,
                                           **({"valor": str(x.valor)} if x.valor is not None else {})}
        return {
            "turno_primera_revelacion_de_deuda": m(self.revela_deuda),
            "turno_solicitud_digitos": m(self.pide_digitos),
            "digitos_coinciden_con_datos_cliente": self.digitos_coinciden,
            "monto_informado_por_agente": m(self.monto_informado),
            "fecha_vencimiento_informada_por_agente": m(self.fecha_vencimiento_informada),
            "terminos_prohibidos_detectados": [m(t) for t in self.terminos_prohibidos],
            "cliente_colgo_antes_del_cierre": self.cliente_colgo,
            "ultimo_turno_agente": self.ultimo_turno_agente,
        }


def _revelaciones(turno: Turno, idx: int, producto_plegado: str, ref: dt.date) -> list[Mencion]:
    texto, plegado = turno.texto, plegar(turno.texto)
    hallazgos: list[Mencion] = []
    for monto in encontrar_montos(texto):
        hallazgos.append(Mencion(idx, oracion_en(texto, monto.inicio), "monto"))
    pos = plegado.find(producto_plegado)
    if pos != -1:
        hallazgos.append(Mencion(idx, oracion_en(texto, pos), "producto"))
    for rx, tipo in ((RE_PRODUCTO_GENERICO, "producto"), (RE_DEUDA, "deuda")):
        m = rx.search(plegado)
        if m:
            hallazgos.append(Mencion(idx, oracion_en(texto, m.start()), tipo))
    for f in encontrar_fechas_con_mes(texto, ref):
        hallazgos.append(Mencion(idx, oracion_en(texto, f.inicio), "fecha"))
    return hallazgos


def calcular_hechos(conv: Conversacion) -> HechosCodigo:
    tr = conv.transcripcion
    datos = conv.datos_cliente
    nombre = " ".join(plegar(datos.nombre).split())
    producto = " ".join(plegar(datos.producto).split())
    agente = [i for i, t in enumerate(tr, start=1) if t.hablante == "agente"]
    h = HechosCodigo(turnos_agente=agente, ventana_presentacion=[],
                     ultimo_turno_agente=agente[-1] if agente else None)

    # Revelación de información de la deuda (cualquier turno del agente).
    for i in agente:
        h.revelaciones.extend(_revelaciones(tr[i - 1], i, producto, conv.fecha_llamada))
    if h.revelaciones:
        h.revela_deuda = h.revelaciones[0]
    limite = h.revela_deuda.turno if h.revela_deuda else len(tr) + 1

    # Solicitud de dígitos: primera, en o antes de la revelación.
    for i in agente:
        plegado = plegar(tr[i - 1].texto)
        m = RE_PIDE_DIGITOS.search(plegado)
        if m:
            h.pide_digitos = Mencion(i, oracion_en(tr[i - 1].texto, m.start()))
            break

    # Ventana de presentación: 2 primeros turnos del agente, cortada en el primero que pide datos o revela.
    for i in agente[:2]:
        h.ventana_presentacion.append(i)
        if (h.pide_digitos and i >= h.pide_digitos.turno) or i >= limite:
            break
    for i in h.ventana_presentacion:
        texto, plegado = tr[i - 1].texto, plegar(tr[i - 1].texto)
        for atributo, rx in (("lina", RE_LINA), ("empresa", RE_EMPRESA),
                             ("asistente_virtual", RE_VIRTUAL), ("grabacion", RE_GRABACION)):
            m = rx.search(plegado)
            if m and getattr(h, atributo) is None:
                setattr(h, atributo, Mencion(i, oracion_en(texto, m.start())))

    # Pregunta por el titular con nombre completo y respuesta del interlocutor.
    for i in agente:
        texto, plegado = tr[i - 1].texto, plegar(tr[i - 1].texto)
        pos = " ".join(plegado.split()).find(nombre)
        if pos != -1 and RE_PREGUNTA_IDENTIDAD.search(plegado):
            pos_real = plegado.find(nombre.split()[0])
            if h.confirma_nombre is None and i <= limite:
                h.confirma_nombre = Mencion(i, oracion_en(texto, max(pos_real, 0)))
        if (pos != -1 or re.search(r"\bhablo con\b", plegado)) and h.es_titular_heuristico is None:
            respuesta = next((j for j in range(i + 1, len(tr) + 1) if tr[j - 1].hablante == "cliente"), None)
            if respuesta:
                r = plegar(tr[respuesta - 1].texto)
                if RE_NO_TITULAR.search(r):
                    h.es_titular_heuristico = False
                elif RE_SI_TITULAR.search(r):
                    h.es_titular_heuristico = True
                if h.es_titular_heuristico is not None:
                    h.respuesta_identidad = Mencion(respuesta, tr[respuesta - 1].texto.strip())

    # Dígitos dichos por el cliente entre la solicitud y la revelación (vale el último intento).
    if h.pide_digitos:
        fin = limite if h.revela_deuda else len(tr) + 1
        for j in range(h.pide_digitos.turno + 1, fin):
            if tr[j - 1].hablante != "cliente":
                continue
            dichos = extraer_digitos(tr[j - 1].texto)
            if len(dichos) >= 4 or (dichos and h.digitos_cliente is None):
                h.digitos_cliente = Mencion(j, tr[j - 1].texto.strip(), dichos)
        if h.digitos_cliente:
            h.digitos_coinciden = coinciden(str(h.digitos_cliente.valor), datos.ultimos4_documento)

    # Monto informado: primera mención de un monto por el agente.
    for i in agente:
        montos = encontrar_montos(tr[i - 1].texto)
        if montos:
            h.monto_informado = Mencion(i, montos[0].texto, montos[0].valor)
            break

    # Fecha de vencimiento informada: primera fecha con mes en un turno del agente que habla de vencimiento.
    for i in agente:
        texto, plegado = tr[i - 1].texto, plegar(tr[i - 1].texto)
        kw = RE_VENCIMIENTO.search(plegado)
        if not kw:
            continue
        fechas = encontrar_fechas_con_mes(texto, conv.fecha_llamada)
        if fechas:
            elegida = next((f for f in fechas if f.inicio >= kw.start()), fechas[0])
            h.fecha_vencimiento_informada = Mencion(i, elegida.texto, elegida.fecha)
            break

    # Términos prohibidos (solo en turnos del agente).
    for i in agente:
        texto = tr[i - 1].texto
        for m in RE_PROHIBIDOS.finditer(plegar(texto)):
            h.terminos_prohibidos.append(Mencion(i, oracion_en(texto, m.start()), texto[m.start():m.end()]))

    ultimo = tr[-1]
    h.cliente_colgo = ultimo.hablante == "sistema" and bool(RE_CLIENTE_COLGO.search(plegar(ultimo.texto)))
    return h


# ------------------------------------------------------------------ criterios por código

def resultado(criterio_id: str, res: str, evidencia: list[Cita], explicacion: str,
              severidad: str | None = None, metodo: str | None = None) -> ResultadoCriterio:
    c = POR_ID[criterio_id]
    if res == "no_cumple" and severidad is None:
        severidad = c.severidad
    return ResultadoCriterio(criterio_id=c.id, regla=c.regla, nombre=c.nombre, resultado=res,
                             evidencia=evidencia, explicacion=explicacion,
                             severidad=severidad if res == "no_cumple" else None,
                             metodo=metodo or c.metodo)


def _cita(tr: list[Turno], m: Mencion) -> Cita:
    return cita_turno(tr, m.turno, m.texto)


def criterios_codigo(conv: Conversacion, h: HechosCodigo, es_titular: bool | None) -> dict[str, ResultadoCriterio]:
    """R1a, R1b, R2a, R2b, R4a, R4b y la parte de términos prohibidos de R10 (si hay hallazgo)."""
    tr = conv.transcripcion
    datos = conv.datos_cliente
    out: dict[str, ResultadoCriterio] = {}
    primer_agente = h.turnos_agente[0] if h.turnos_agente else 1
    omision = [cita_turno(tr, primer_agente)]

    # R1a
    faltan = [n for n, v in (("el nombre Lina", h.lina), ("que es asistente virtual", h.asistente_virtual),
                             ("Banco Andino", h.empresa)) if v is None]
    if not faltan:
        ev = list({m.turno: _cita(tr, m) for m in (h.lina, h.asistente_virtual, h.empresa)}.values())
        out["R1a"] = resultado("R1a", "cumple", ev, "Se presenta como Lina, asistente virtual de Banco Andino, "
                                                    "al inicio de la llamada.")
    else:
        out["R1a"] = resultado("R1a", "no_cumple", omision,
                               f"En sus primeros turnos no menciona {', '.join(faltan)}.")
    # R1b
    if h.grabacion:
        out["R1b"] = resultado("R1b", "cumple", [_cita(tr, h.grabacion)], "Informa que la llamada está siendo grabada.")
    else:
        out["R1b"] = resultado("R1b", "no_cumple", omision,
                               "No informa que la llamada está siendo grabada al inicio.")
    # R2a
    if h.confirma_nombre:
        out["R2a"] = resultado("R2a", "cumple", [_cita(tr, h.confirma_nombre)],
                               "Pregunta por el titular usando su nombre completo.")
    else:
        out["R2a"] = resultado("R2a", "no_cumple", omision,
                               f"No confirma que habla con {datos.nombre} usando su nombre completo.")

    # R2b, R4a, R4b dependen de si el interlocutor es el titular.
    if es_titular is None:
        for cid in ("R2b", "R4a", "R4b"):
            out[cid] = resultado(cid, "no_evaluado", [], "No se pudo determinar si el interlocutor es el titular.")
    elif not es_titular:
        for cid in ("R2b", "R4a", "R4b"):
            out[cid] = resultado(cid, "no_aplica", [], "El interlocutor no es el titular; se evalúa en R3.")
    else:
        out["R2b"] = _r2b(tr, h, datos.ultimos4_documento)
        out["R4a"] = _r4a(tr, h, datos.monto_vencido_cop)
        out["R4b"] = _r4b(tr, h, datos.fecha_vencimiento)
    return out


def _r2b(tr: list[Turno], h: HechosCodigo, esperados: str) -> ResultadoCriterio:
    if h.revela_deuda is None:
        return resultado("R2b", "no_aplica", [], "El agente no revela información de la deuda.")
    rev = _cita(tr, h.revela_deuda)
    if h.pide_digitos is None or h.pide_digitos.turno > h.revela_deuda.turno:
        return resultado("R2b", "no_cumple", [rev], f"Revela información de la deuda (turno {rev.turno}) sin "
                                                   "haber pedido los últimos 4 dígitos del documento.")
    if h.pide_digitos.turno == h.revela_deuda.turno:
        return resultado("R2b", "no_cumple", [rev], "Revela información de la deuda en el mismo turno en que "
                                                   "pide los dígitos, antes de verificarlos.")
    if h.digitos_cliente is None:
        return resultado("R2b", "no_cumple", [_cita(tr, h.pide_digitos), rev],
                         "Pide los dígitos pero revela la deuda sin que el cliente los haya dado.")
    dichos = _cita(tr, h.digitos_cliente)
    if not h.digitos_coinciden:
        return resultado("R2b", "no_cumple", [dichos, rev],
                         f"El cliente dice '{h.digitos_cliente.valor}' y el registro termina en {esperados}; "
                         "aun así el agente revela la deuda.")
    return resultado("R2b", "cumple", [_cita(tr, h.pide_digitos), dichos],
                     "Pide los 4 dígitos y coinciden antes de revelar la deuda.")


def _formato_cop(valor: int) -> str:
    return f"${valor:,.0f}".replace(",", ".")


def _r4a(tr: list[Turno], h: HechosCodigo, esperado: int) -> ResultadoCriterio:
    if h.monto_informado is None:
        return resultado("R4a", "no_aplica", [], "El agente no informa el monto vencido.")
    cita = _cita(tr, h.monto_informado)
    if h.monto_informado.valor == esperado:
        return resultado("R4a", "cumple", [cita], f"Informa {_formato_cop(esperado)}, igual a datos_cliente.")
    return resultado("R4a", "no_cumple", [cita], f"Informa {_formato_cop(h.monto_informado.valor)} pero el "
                                                 f"monto vencido es {_formato_cop(esperado)}.")


def _r4b(tr: list[Turno], h: HechosCodigo, esperada: dt.date) -> ResultadoCriterio:
    f = h.fecha_vencimiento_informada
    if f is None:
        return resultado("R4b", "no_aplica", [], "El agente no informa la fecha de vencimiento.")
    cita = _cita(tr, f)
    if f.valor is not None and (f.valor.month, f.valor.day) == (esperada.month, esperada.day):
        return resultado("R4b", "cumple", [cita], f"Informa el vencimiento {esperada.isoformat()}, igual a datos_cliente.")
    informada = f.valor.isoformat() if f.valor else f"'{f.texto}'"
    return resultado("R4b", "no_cumple", [cita], f"Informa el vencimiento {informada} pero en datos_cliente es "
                                                 f"{esperada.isoformat()}.")


def r10_por_terminos(tr: list[Turno], h: HechosCodigo) -> ResultadoCriterio | None:
    """Mención de acciones legales/embargo/centrales de riesgo: no_cumple crítico, decide el código."""
    if not h.terminos_prohibidos:
        return None
    terminos = sorted({str(t.valor) for t in h.terminos_prohibidos})
    unicas = list({(t.turno, t.texto): t for t in h.terminos_prohibidos}.values())
    return resultado("R10", "no_cumple", [_cita(tr, t) for t in unicas[:3]],
                     f"El agente menciona términos prohibidos: {', '.join(terminos)}.", severidad="critica")
