import os
import sys
import pytest

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set dummy env vars for testing
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-123")
os.environ.setdefault("RSMEANS_API_KEY", "test-rsmeans-key-123")
os.environ.setdefault("RSMEANS_BASE_URL", "https://api.gordian.com/v1")


@pytest.fixture
def sample_jpeg_bytes():
    """Create a minimal valid JPEG for testing."""
    from PIL import Image
    import io
    img = Image.new("RGB", (100, 100), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def sample_png_bytes():
    """Create a minimal valid PNG for testing."""
    from PIL import Image
    import io
    img = Image.new("RGB", (100, 100), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def sample_vision_response():
    """Sample Claude Vision API response."""
    return {
        "materials": [
            {
                "name": "2x4 lumber",
                "quantity": 50,
                "unit": "lf",
                "confidence": "high",
                "notes": "Stacked framing lumber clearly visible",
            },
            {
                "name": "plywood sheathing",
                "quantity": 200,
                "unit": "sqft",
                "confidence": "medium",
                "notes": "Wall sheathing partially visible",
            },
            {
                "name": "concrete block",
                "quantity": 80,
                "unit": "ea",
                "confidence": "low",
                "notes": "Foundation blocks partially obscured",
            },
        ],
        "scene_description": "Residential construction site showing wood framing in progress",
        "limitations": "Rear of structure not visible, some materials obscured by scaffolding",
    }


@pytest.fixture
def sample_rsmeans_response():
    """Sample RSMeans API response for a single material."""
    return {
        "results": [
            {
                "lineNumber": "06 11 10.10 0020",
                "description": "Lumber, framing, 2x4, 8' long",
                "unit": "lf",
                "unitCost": 1.85,
                "materialCost": 0.95,
                "laborCost": 0.90,
            }
        ]
    }
