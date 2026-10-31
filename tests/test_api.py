"""Endpoints con TestClient; el LLM se reemplaza por uno simulado que falla (modo degradado)."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.evaluator import Evaluador
from app.llm.base import ErrorLLM

FIX = json.loads((Path(__file__).parent / "fixtures" / "sinteticas.json").read_text(encoding="utf-8"))


class LLMCaido:
    modelo = "caido"

    async def generar_json(self, *a, **k):
        raise ErrorLLM("503 UNAVAILABLE")


@pytest.fixture()
def cliente(monkeypatch):
    monkeypatch.setattr(main, "EVALUADOR", Evaluador(LLMCaido(), main.SPEC_DEFECTO))
    return TestClient(main.app)


def test_health_y_rubrica(cliente):
    assert cliente.get("/health").json()["estado"] == "ok"
    rubrica = cliente.get("/rubrica").json()
    assert [c["id"] for c in rubrica][:3] == ["R1a", "R1b", "R2a"] and len(rubrica) == 13


def test_raiz_redirige_a_ui(cliente):
    r = cliente.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/ui"


def test_evaluate_degradado_responde_200(cliente):
    conv = {k: v for k, v in FIX["conversaciones"][1].items() if k != "esperado"}
    r = cliente.post("/evaluate", json=conv)
    assert r.status_code == 200
    body = r.json()
    assert body["estado_evaluacion"] == "parcial" and len(body["criterios"]) == 13
    assert any("503" in e for e in body["metadatos"]["errores"])


def test_evaluate_batch_y_upload(cliente):
    archivo = {"conversaciones": FIX["conversaciones"][:2]}
    r = cliente.post("/evaluate/batch", json=archivo)
    assert r.status_code == 200 and len(r.json()["evaluaciones"]) == 2
    r = cliente.post("/evaluate/batch/upload",
                     files={"archivo": ("a.json", json.dumps(archivo).encode(), "application/json")})
    assert r.status_code == 200 and r.json()["reporte_agregado"]["total_conversaciones"] == 2


@pytest.mark.parametrize("cuerpo", [
    {"id": "X"},                                                     # faltan campos
    {"id": "X", "fecha_llamada": "2026-13-40", "datos_cliente": {}, "transcripcion": []},
])
def test_evaluate_entrada_invalida_422(cliente, cuerpo):
    r = cliente.post("/evaluate", json=cuerpo)
    assert r.status_code == 422 and r.json()["error"] == "entrada inválida"


def test_upload_no_json_422(cliente):
    r = cliente.post("/evaluate/batch/upload", files={"archivo": ("a.json", b"{no json", "application/json")})
    assert r.status_code == 422
    r = cliente.post("/evaluate/batch/upload", files={"archivo": ("a.json", b'{"conversaciones": []}', "application/json")})
    assert r.status_code == 422


def test_evaluate_reusa_la_cache_del_lote(monkeypatch):
    from tests.test_evaluator import LLMFalso, respuesta
    llm = LLMFalso([respuesta()])
    monkeypatch.setattr(main, "EVALUADOR", Evaluador(llm, main.SPEC_DEFECTO))
    cliente = TestClient(main.app)
    conv = FIX["conversaciones"][0]
    assert cliente.post("/evaluate/batch", json={"conversaciones": [conv]}).status_code == 200
    r = cliente.post("/evaluate", json=conv)
    assert r.status_code == 200 and r.json()["metadatos"]["desde_cache"] is True and llm.llamadas == 1


def test_batch_ids_repetidos_422(cliente):
    conv = FIX["conversaciones"][0]
    r = cliente.post("/evaluate/batch", json={"conversaciones": [conv, conv]})
    assert r.status_code == 422
