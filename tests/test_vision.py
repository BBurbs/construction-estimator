import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.vision import analyze_image, VisionRefusalError, EmptyAnalysisError


class TestAnalyzeImage:
    @pytest.mark.asyncio
    async def test_successful_analysis(self, sample_jpeg_bytes, sample_vision_response):
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=json.dumps(sample_vision_response))]
        mock_message.stop_reason = "end_turn"

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        with patch("app.vision.anthropic.AsyncAnthropic", return_value=mock_client):
            result = await analyze_image("test-key", sample_jpeg_bytes)

        assert len(result["materials"]) == 3
        assert result["materials"][0]["name"] == "2x4 lumber"
        assert result["scene_description"] == "Residential construction site showing wood framing in progress"

    @pytest.mark.asyncio
    async def test_handles_markdown_wrapped_json(self, sample_jpeg_bytes, sample_vision_response):
        wrapped = f"```json\n{json.dumps(sample_vision_response)}\n```"

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=wrapped)]
        mock_message.stop_reason = "end_turn"

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        with patch("app.vision.anthropic.AsyncAnthropic", return_value=mock_client):
            result = await analyze_image("test-key", sample_jpeg_bytes)

        assert len(result["materials"]) == 3

    @pytest.mark.asyncio
    async def test_empty_materials_raises(self, sample_jpeg_bytes):
        response = {"scene_description": "Empty lot", "limitations": "Nothing here"}
        # Missing 'materials' key
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=json.dumps(response))]
        mock_message.stop_reason = "end_turn"

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        with patch("app.vision.anthropic.AsyncAnthropic", return_value=mock_client):
            with pytest.raises(EmptyAnalysisError):
                await analyze_image("test-key", sample_jpeg_bytes)

    @pytest.mark.asyncio
    async def test_refusal_detected(self, sample_jpeg_bytes):
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="I'm sorry, I cannot analyze this image as it appears to contain sensitive content.")]
        mock_message.stop_reason = "end_turn"

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        with patch("app.vision.anthropic.AsyncAnthropic", return_value=mock_client):
            with pytest.raises(VisionRefusalError):
                await analyze_image("test-key", sample_jpeg_bytes)
