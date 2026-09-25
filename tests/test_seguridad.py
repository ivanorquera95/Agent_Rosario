# Las cabeceras y el limite de tamano se prueban contra la app real, sin red.
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.getenv("DATABASE_URL_TEST", ""))
    from api.main import app
    with TestClient(app) as c:
        yield c


def test_cabeceras_de_seguridad(cliente):
    r = cliente.get("/salud")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert "microphone=(self)" in r.headers["Permissions-Policy"]


def test_cuerpo_demasiado_grande(cliente):
    from api.seguridad import MAX_BYTES_CUERPO
    r = cliente.post(
        "/chat",
        content=b"x" * (MAX_BYTES_CUERPO + 1),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 413


def test_docs_cerrados(cliente):
    assert cliente.get("/docs").status_code == 404
    assert cliente.get("/openapi.json").status_code == 404