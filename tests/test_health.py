"""
Integration tests for root endpoints.
Verify that the server starts correctly and responds to basic requests:
GET / and GET /health.
"""


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to StudaFly API"}


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
