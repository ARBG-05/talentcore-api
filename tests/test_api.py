import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Base, engine, get_db, Empleado, SolicitudVacaciones


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ac01_solicitud_valida_y_calculo_saldo(client):
    # Crear ADMIN_RRHH (id=1)
    admin_payload = {
        "nombre": "Admin",
        "email": "admin@talentcore.com",
        "rol": "ADMIN_RRHH",
        "anios_antiguedad": 5
    }
    response = client.post("/api/v1/empleados", json=admin_payload)
    assert response.status_code == 201
    admin_id = response.json()["id"]
    assert admin_id == 1

    # Crear MANAGER (id=2) usando header X-User-Id
    manager_payload = {
        "nombre": "Manager",
        "email": "manager@talentcore.com",
        "rol": "MANAGER",
        "anios_antiguedad": 3
    }
    headers = {"X-User-Id": "1"}
    response = client.post("/api/v1/empleados", json=manager_payload, headers=headers)
    assert response.status_code == 201
    manager_id = response.json()["id"]
    assert manager_id == 2

    # Crear EMPLEADO (id=3, anios_antiguedad=3, manager_id=2)
    employee_payload = {
        "nombre": "Empleado",
        "email": "empleado@talentcore.com",
        "rol": "EMPLEADO",
        "anios_antiguedad": 3,
        "manager_id": 2
    }
    response = client.post("/api/v1/empleados", json=employee_payload, headers=headers)
    assert response.status_code == 201
    employee_id = response.json()["id"]
    assert employee_id == 3

    # Verificar saldo inicial: anios_antiguedad=3 -> min(12 + 2*(3-1), 20) = min(16, 20) = 16
    response = client.get(f"/api/v1/vacaciones/saldo/{employee_id}")
    assert response.status_code == 200
    saldo_data = response.json()
    assert saldo_data["dias_totales"] == 16
    assert saldo_data["dias_aprobados"] == 0
    assert saldo_data["saldo_disponible"] == 16

    # Solicitar 5 días
    solicitud_payload = {
        "empleado_id": employee_id,
        "dias_solicitados": 5,
        "motivo": "Vacaciones de verano"
    }
    response = client.post("/api/v1/vacaciones/solicitar", json=solicitud_payload)
    assert response.status_code == 201
    solicitud_data = response.json()
    assert solicitud_data["estado"] == "PENDING"
    solicitud_id = solicitud_data["id"]

    # Manager aprueba la solicitud
    revision_payload = {"accion": "APPROVE"}
    headers_manager = {"X-User-Id": "2"}
    response = client.post(f"/api/v1/vacaciones/{solicitud_id}/revisar", json=revision_payload, headers=headers_manager)
    assert response.status_code == 200
    assert response.json()["estado"] == "APPROVED"

    # Verificar nuevo saldo: 16 - 5 = 11
    response = client.get(f"/api/v1/vacaciones/saldo/{employee_id}")
    assert response.status_code == 200
    saldo_data = response.json()
    assert saldo_data["dias_totales"] == 16
    assert saldo_data["dias_aprobados"] == 5
    assert saldo_data["saldo_disponible"] == 11


def test_ac02_saldo_insuficiente(client):
    # Crear ADMIN_RRHH (id=1)
    admin_payload = {
        "nombre": "Admin",
        "email": "admin@talentcore.com",
        "rol": "ADMIN_RRHH",
        "anios_antiguedad": 5
    }
    response = client.post("/api/v1/empleados", json=admin_payload)
    assert response.status_code == 201
    admin_id = response.json()["id"]
    assert admin_id == 1

    # Crear EMPLEADO (id=2, anios_antiguedad=1)
    employee_payload = {
        "nombre": "Empleado",
        "email": "empleado@talentcore.com",
        "rol": "EMPLEADO",
        "anios_antiguedad": 1
    }
    headers = {"X-User-Id": "1"}
    response = client.post("/api/v1/empleados", json=employee_payload, headers=headers)
    assert response.status_code == 201
    employee_id = response.json()["id"]
    assert employee_id == 2

    # Intentar solicitar 15 días (saldo disponible es 12)
    solicitud_payload = {
        "empleado_id": employee_id,
        "dias_solicitados": 15
    }
    response = client.post("/api/v1/vacaciones/solicitar", json=solicitud_payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient vacation balance"


def test_ac03_manager_no_autorizado(client):
    # Crear ADMIN_RRHH (id=1)
    admin_payload = {
        "nombre": "Admin",
        "email": "admin@talentcore.com",
        "rol": "ADMIN_RRHH",
        "anios_antiguedad": 5
    }
    response = client.post("/api/v1/empleados", json=admin_payload)
    assert response.status_code == 201
    admin_id = response.json()["id"]
    assert admin_id == 1

    # Crear MANAGER A (id=2)
    manager_a_payload = {
        "nombre": "Manager A",
        "email": "manager_a@talentcore.com",
        "rol": "MANAGER",
        "anios_antiguedad": 3
    }
    headers = {"X-User-Id": "1"}
    response = client.post("/api/v1/empleados", json=manager_a_payload, headers=headers)
    assert response.status_code == 201
    manager_a_id = response.json()["id"]
    assert manager_a_id == 2

    # Crear MANAGER B (id=3)
    manager_b_payload = {
        "nombre": "Manager B",
        "email": "manager_b@talentcore.com",
        "rol": "MANAGER",
        "anios_antiguedad": 3
    }
    response = client.post("/api/v1/empleados", json=manager_b_payload, headers=headers)
    assert response.status_code == 201
    manager_b_id = response.json()["id"]
    assert manager_b_id == 3

    # Crear EMPLEADO (id=4, manager_id=2)
    employee_payload = {
        "nombre": "Empleado",
        "email": "empleado@talentcore.com",
        "rol": "EMPLEADO",
        "anios_antiguedad": 2,
        "manager_id": 2
    }
    response = client.post("/api/v1/empleados", json=employee_payload, headers=headers)
    assert response.status_code == 201
    employee_id = response.json()["id"]
    assert employee_id == 4

    # El empleado solicita 3 días
    solicitud_payload = {
        "empleado_id": employee_id,
        "dias_solicitados": 3
    }
    response = client.post("/api/v1/vacaciones/solicitar", json=solicitud_payload)
    assert response.status_code == 201
    solicitud_id = response.json()["id"]

    # MANAGER B intenta aprobar (no es el manager directo)
    revision_payload = {"accion": "APPROVE"}
    headers_manager_b = {"X-User-Id": "3"}
    response = client.post(f"/api/v1/vacaciones/{solicitud_id}/revisar", json=revision_payload, headers=headers_manager_b)
    assert response.status_code == 403
    assert response.json()["detail"] == "Unauthorized: Not the direct manager"
