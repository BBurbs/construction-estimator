import base64
import json
import logging

import anthropic

from app.utils import retry_with_backoff

logger = logging.getLogger(__name__)


class VisionRefusalError(Exception):
    """Claude refused to analyze the image."""
    pass


class EmptyAnalysisError(Exception):
    """Claude returned no materials from the image."""
    pass


VISION_PROMPT = """Analyze this construction site photo. Identify all visible construction materials and estimate quantities.

For each material you can identify, return:
- name: The common construction material name (e.g., "2x4 lumber", "concrete block 8x8x16", "1/2 inch drywall", "copper pipe 3/4 inch")
- quantity: Your best estimate of the quantity visible
- unit: The standard unit of measure (sqft, lf, ea, cuyd, etc.)
- confidence: Your confidence in the quantity estimate — "high" (clearly countable/measurable), "medium" (reasonable estimate from visible area), or "low" (rough guess, partially obscured)
- notes: Brief note on what you see and any caveats

Return ONLY valid JSON in this exact format, no other text:
{
    "materials": [
        {
            "name": "material name",
            "quantity": 100,
            "unit": "sqft",
            "confidence": "medium",
            "notes": "visible on north wall, estimated from partial view"
        }
    ],
    "scene_description": "Brief description of what the photo shows",
    "limitations": "Any limitations in the analysis (obscured areas, poor lighting, etc.)"
}

If you cannot identify any construction materials, return:
{"materials": [], "scene_description": "...", "limitations": "No construction materials visible"}

Be specific with material names — use industry-standard terms that would match RSMeans cost data entries."""


@retry_with_backoff(
    max_retries=2,
    base_delay=1.0,
    exceptions=(anthropic.APITimeoutError, anthropic.RateLimitError, json.JSONDecodeError),
)
async def analyze_image(api_key: str, jpeg_bytes: bytes) -> dict:
    """Send image to Claude Vision API and get structured material analysis.

    Args:
        api_key: Anthropic API key
        jpeg_bytes: JPEG image bytes

    Returns:
        Dict with materials list, scene_description, and limitations.

    Raises:
        VisionRefusalError: Claude refused to analyze
        EmptyAnalysisError: No materials found
        anthropic.APITimeoutError: After retries exhausted
        anthropic.RateLimitError: After retries exhausted
    """
    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=60.0)

    image_b64 = base64.b64encode(jpeg_bytes).decode("utf-8")

    logger.info("Sending image to Claude Vision (%d bytes)", len(jpeg_bytes))

    message = await client.messages.create(
        model="claude-sonnet-4-6-20250514",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": VISION_PROMPT,
                    },
                ],
            }
        ],
    )

    response_text = message.content[0].text
    logger.info("Claude Vision response received (%d chars)", len(response_text))

    # Check for refusal
    if message.stop_reason == "end_turn" and any(
        phrase in response_text.lower()
        for phrase in ["i cannot", "i'm unable", "i can't", "sorry"]
    ):
        if "materials" not in response_text:
            raise VisionRefusalError(f"Claude refused to analyze: {response_text[:200]}")

    # Parse JSON response
    # Handle case where Claude wraps JSON in markdown code blocks
    clean_text = response_text.strip()
    if clean_text.startswith("```"):
        clean_text = clean_text.split("\n", 1)[1] if "\n" in clean_text else clean_text
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()

    result = json.loads(clean_text)

    # Validate structure
    if "materials" not in result:
        raise EmptyAnalysisError("Response missing 'materials' key")

    material_count = len(result["materials"])
    logger.info(
        "Analysis complete: %d materials found, scene: %s",
        material_count,
        result.get("scene_description", "N/A")[:100],
    )

    return result
