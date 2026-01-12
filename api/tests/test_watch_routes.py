from fastapi.testclient import TestClient

from app.main import create_app


def test_watch_resolve_route_registered() -> None:
    app = create_app()
    app.router.on_startup.clear()
    client = TestClient(app)
    response = client.post(
        "/api/watch/resolve",
        json={"title_id": 1, "audio_id": 1, "quality_id": 1},
    )
    assert response.status_code in {401, 422}
