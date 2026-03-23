import io
import pytest
from PIL import Image

from app.image_utils import validate_image, strip_exif, convert_to_jpeg, process_upload, ImageValidationError


class TestValidateImage:
    def test_valid_jpeg(self, sample_jpeg_bytes):
        img = validate_image("image/jpeg", len(sample_jpeg_bytes), sample_jpeg_bytes)
        assert img is not None
        assert img.size == (100, 100)

    def test_valid_png(self, sample_png_bytes):
        img = validate_image("image/png", len(sample_png_bytes), sample_png_bytes)
        assert img is not None

    def test_reject_unsupported_mime(self, sample_jpeg_bytes):
        with pytest.raises(ImageValidationError, match="Unsupported image type"):
            validate_image("application/pdf", len(sample_jpeg_bytes), sample_jpeg_bytes)

    def test_reject_svg(self, sample_jpeg_bytes):
        with pytest.raises(ImageValidationError, match="Unsupported image type"):
            validate_image("image/svg+xml", len(sample_jpeg_bytes), sample_jpeg_bytes)

    def test_reject_too_large(self, sample_jpeg_bytes):
        with pytest.raises(ImageValidationError, match="too large"):
            validate_image("image/jpeg", 25 * 1024 * 1024, sample_jpeg_bytes)

    def test_reject_empty(self):
        with pytest.raises(ImageValidationError, match="Empty file"):
            validate_image("image/jpeg", 0, b"")

    def test_reject_corrupt(self):
        with pytest.raises(ImageValidationError, match="Could not read"):
            validate_image("image/jpeg", 100, b"not an image at all")

    def test_reject_renamed_text_file(self):
        content = b"This is actually a text file pretending to be a JPEG"
        with pytest.raises(ImageValidationError, match="Could not read"):
            validate_image("image/jpeg", len(content), content)


class TestStripExif:
    def test_strips_exif_data(self):
        # Create image with EXIF-like data
        img = Image.new("RGB", (50, 50), color="green")
        cleaned = strip_exif(img)
        assert cleaned.size == (50, 50)
        # Cleaned image should have no EXIF info
        assert not hasattr(cleaned, "_getexif") or cleaned._getexif() is None

    def test_preserves_rgba(self):
        img = Image.new("RGBA", (50, 50), color=(255, 0, 0, 128))
        cleaned = strip_exif(img)
        assert cleaned.mode == "RGBA"
        assert cleaned.size == (50, 50)


class TestConvertToJpeg:
    def test_rgb_to_jpeg(self):
        img = Image.new("RGB", (50, 50), color="red")
        jpeg_bytes = convert_to_jpeg(img)
        assert jpeg_bytes[:2] == b'\xff\xd8'  # JPEG magic bytes

    def test_rgba_to_jpeg(self):
        img = Image.new("RGBA", (50, 50), color=(255, 0, 0, 128))
        jpeg_bytes = convert_to_jpeg(img)
        assert jpeg_bytes[:2] == b'\xff\xd8'

    def test_palette_to_jpeg(self):
        img = Image.new("P", (50, 50))
        jpeg_bytes = convert_to_jpeg(img)
        assert jpeg_bytes[:2] == b'\xff\xd8'


class TestProcessUpload:
    def test_full_pipeline(self, sample_jpeg_bytes, tmp_path, monkeypatch):
        import app.image_utils
        monkeypatch.setattr(app.image_utils, "UPLOAD_DIR", tmp_path)

        filename, jpeg_bytes = process_upload(
            content_type="image/jpeg",
            file_size=len(sample_jpeg_bytes),
            file_bytes=sample_jpeg_bytes,
            original_filename="test_photo.jpg",
        )

        assert filename.endswith(".jpg")
        assert len(jpeg_bytes) > 0
        assert (tmp_path / filename).exists()

    def test_rejects_invalid(self):
        with pytest.raises(ImageValidationError):
            process_upload(
                content_type="text/plain",
                file_size=100,
                file_bytes=b"not an image",
                original_filename="fake.txt",
            )
