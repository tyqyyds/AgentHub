import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock


@pytest.fixture
def client():
    from backend.api.main import app
    return TestClient(app)


def test_plan_execute_endpoint_exists(client):
    response = client.post(
        "/api/v1/knowledge/plan-execute",
        json={"message": "帮我规划网络优化方案", "context": {"route": "/", "role": "admin"}},
        headers={"Authorization": "Bearer test_token"},
    )
    assert response.status_code in (200, 401, 422)
