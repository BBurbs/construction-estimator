import io
import uuid
import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB

UPLOAD_DIR = Path(__file__).parent.parent / "uploads"


class ImageValidationError(Exception):
    """Raised when image validation fails."""
    pass


def _register_heif():
    """Register HEIF/HEIC support with Pillow."""
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        logger.warning("pillow-heif not installed — HEIC support unavailable")


_register_heif()


def validate_image(content_type: str, file_size: int, file_bytes: bytes) -> Image.Image:
    """Validate uploaded image: MIME type, size, and integrity.

    Returns a Pillow Image object if valid.
    Raises ImageValidationError with a user-friendly message if not.
    """
    # Check MIME type
    if content_type not in ALLOWED_MIME_TYPES:
        raise ImageValidationError(
            f"Unsupported image type: {content_type}. "
            f"Accepted: JPEG, PNG, WebP, HEIC."
        )

    # Check file size
    if file_size > MAX_FILE_SIZE:
        size_mb = file_size / (1024 * 1024)
        raise ImageValidationError(
            f"Image too large: {size_mb:.1f}MB. Maximum: 20MB."
        )

    if file_size == 0:
        raise ImageValidationError("Empty file uploaded.")

    # Verify it's a real image by opening with Pillow
    try:
        img = Image.open(io.BytesIO(file_bytes))
        img.verify()
        # Re-open after verify (verify closes the file)
        img = Image.open(io.BytesIO(file_bytes))
    except Exception as e:
        raise ImageValidationError(
            f"Could not read image file: {e}"
        )

    return img


def strip_exif(img: Image.Image) -> Image.Image:
    """Remove EXIF metadata (GPS, camera info, etc.) from image."""
    if img.mode in ("RGBA", "LA", "PA"):
        clean = Image.new(img.mode, img.size)
    else:
        clean = Image.new(img.mode, img.size)
    clean.putdata(list(img.getdata()))
    return clean


def convert_to_jpeg(img: Image.Image) -> bytes:
    """Convert any image to JPEG bytes for consistent processing."""
    if img.mode in ("RGBA", "LA", "PA", "P"):
        img = img.convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def save_image(file_bytes: bytes, original_filename: str) -> str:
    """Save image with a random filename. Returns the saved filename."""
    ext = Path(original_filename).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"):
        ext = ".jpg"

    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = UPLOAD_DIR / filename

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filepath.write_bytes(file_bytes)

    logger.info("Image saved: %s (%d bytes)", filename, len(file_bytes))
    return filename


def process_upload(content_type: str, file_size: int, file_bytes: bytes, original_filename: str) -> tuple[str, bytes]:
    """Full upload pipeline: validate → strip EXIF → convert to JPEG → save.

    Returns (saved_filename, jpeg_bytes).
    """
    img = validate_image(content_type, file_size, file_bytes)
    img = strip_exif(img)
    jpeg_bytes = convert_to_jpeg(img)
    filename = save_image(file_bytes, original_filename)

    logger.info(
        "Upload processed: %s → %s (%d bytes → %d bytes JPEG)",
        original_filename, filename, file_size, len(jpeg_bytes),
    )

    return filename, jpeg_bytes
