import io
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from fastapi.testclient import TestClient
from PIL import Image

# Set env vars before importing app
import os
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["RSMEANS_API_KEY"] = "test-rsmeans-key"

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def jpeg_upload():
    """Create a JPEG file-like object for upload."""
    img = Image.new("RGB", (100, 100), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


class TestEstimateEndpoint:
    def test_no_file(self, client):
        response = client.post("/api/estimate")
        assert response.status_code == 422

    def test_invalid_file_type(self, client):
        response = client.post(
            "/api/estimate",
            files={"file": ("test.txt", b"not an image", "text/plain")},
        )
        assert response.status_code == 422

    def test_successful_estimate(self, client, jpeg_upload, sample_vision_response, sample_rsmeans_response, tmp_path, monkeypatch):
        import app.image_utils
        monkeypatch.setattr(app.image_utils, "UPLOAD_DIR", tmp_path)

        # Mock Claude Vision
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=json.dumps(sample_vision_response))]
        mock_message.stop_reason = "end_turn"
        mock_anthropic = AsyncMock()
        mock_anthropic.messages.create = AsyncMock(return_value=mock_message)

        # Mock RSMeans — patch the entire lookup_multiple to avoid HTTP mocking complexity
        async def mock_lookup_multiple(materials):
            results = []
            for m in materials:
                entry = {**m}
                entry["unit_cost"] = 1.85
                entry["material_cost"] = 0.95
                entry["labor_cost"] = 0.90
                entry["rsmeans_description"] = "Test material"
                entry["rsmeans_code"] = "06 11 10.10 0020"
                entry["line_total"] = round(float(m.get("quantity", 0)) * 1.85, 2)
                results.append(entry)
            return results

        with patch("app.vision.anthropic.AsyncAnthropic", return_value=mock_anthropic), \
             patch("app.rsmeans.RSMeansClient.lookup_multiple", side_effect=mock_lookup_multiple), \
             patch("app.rsmeans.RSMeansClient.close", new_callable=AsyncMock):

            response = client.post(
                "/api/estimate",
                files={"file": ("site.jpg", jpeg_upload, "image/jpeg")},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["material_count"] == 3
        assert "materials" in data
        assert data["total_cost"] > 0
        assert data["scene_description"] is not None


class TestHistoryEndpoints:
    def test_list_estimates_empty(self, client):
        response = client.get("/api/estimates?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert "estimates" in data

    def test_get_nonexistent_estimate(self, client):
        response = client.get("/api/estimates/99999")
        assert response.status_code == 404


class TestRootRedirect:
    def test_root_redirects(self, client):
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 307
        assert "/static/index.html" in response.headers["location"]
