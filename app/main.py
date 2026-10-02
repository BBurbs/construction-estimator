import logging
import os
import time

from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.image_utils import process_upload, ImageValidationError, MAX_FILE_SIZE
from app.vision import analyze_image, VisionRefusalError, EmptyAnalysisError
from app.matcher import match_materials
from app.rsmeans import RSMeansClient, PricingNotFoundError
from app.models import init_db, save_estimate, get_estimates, get_estimate_by_id

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Construction Cost Estimator", version="1.0.0")

# Serve static files (frontend)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize database on startup
init_db()

# API keys from environment
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
RSMEANS_API_KEY = os.getenv("RSMEANS_API_KEY")
RSMEANS_BASE_URL = os.getenv("RSMEANS_BASE_URL", "https://api.gordian.com/v1")


@app.post("/api/estimate")
async def create_estimate(file: UploadFile = File(...)):
    """Upload a construction site photo and get a cost estimate.

    Pipeline: validate image → Claude Vision → match materials → RSMeans pricing → save & return.
    """
    request_id = f"req_{int(time.time() * 1000)}"
    logger.info("Estimate request %s: file=%s, type=%s", request_id, file.filename, file.content_type)

    # Check API keys are configured
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")
    if not RSMEANS_API_KEY:
        raise HTTPException(status_code=500, detail="RSMEANS_API_KEY not configured")

    # Step 1: Read and validate image
    try:
        file_bytes = await file.read(MAX_FILE_SIZE + 1)
        filename, jpeg_bytes = process_upload(
            content_type=file.content_type or "application/octet-stream",
            file_size=len(file_bytes),
            file_bytes=file_bytes,
            original_filename=file.filename or "upload.jpg",
        )
        logger.info("%s: Image validated and saved as %s", request_id, filename)
    except ImageValidationError as e:
        logger.warning("%s: Validation failed: %s", request_id, str(e))
        return JSONResponse(status_code=422, content={"error": str(e)})

    # Step 2: Analyze with Claude Vision
    try:
        analysis = await analyze_image(ANTHROPIC_API_KEY, jpeg_bytes)
        logger.info(
            "%s: Vision analysis complete — %d materials, scene: %s",
            request_id, len(analysis.get("materials", [])),
            analysis.get("scene_description", "N/A")[:80],
        )
    except VisionRefusalError as e:
        logger.warning("%s: Vision refusal: %s", request_id, str(e))
        return JSONResponse(
            status_code=422,
            content={"error": "Could not analyze this image. Please try a clearer construction site photo."},
        )
    except EmptyAnalysisError:
        logger.info("%s: No materials detected", request_id)
        return JSONResponse(
            status_code=200,
            content={
                "scene_description": "",
                "limitations": "The analysis did not return a usable material list.",
                "materials": [],
                "total_cost": 0,
                "material_count": 0,
                "priced_count": 0,
            },
        )
    except Exception as e:
        logger.error("%s: Vision error: %s: %s", request_id, type(e).__name__, str(e))
        return JSONResponse(
            status_code=500,
            content={"error": "Image analysis failed. Please try again."},
        )

    materials = analysis.get("materials", [])
    if not materials:
        return JSONResponse(
            status_code=200,
            content={
                "scene_description": analysis.get("scene_description", ""),
                "limitations": "No construction materials detected in this image.",
                "materials": [],
                "total_cost": 0,
                "material_count": 0,
                "priced_count": 0,
            },
        )

    # Step 3: Match materials to RSMeans codes
    matched_materials = match_materials(materials)
    logger.info("%s: Material matching complete", request_id)

    # Step 4: Look up costs from RSMeans API (concurrent)
    rsmeans_client = RSMeansClient(api_key=RSMEANS_API_KEY, base_url=RSMEANS_BASE_URL)
    try:
        priced_materials = await rsmeans_client.lookup_multiple(matched_materials)
    finally:
        await rsmeans_client.close()

    total_cost = sum(m.get("line_total", 0) for m in priced_materials)
    priced_count = sum(1 for m in priced_materials if "line_total" in m)

    logger.info(
        "%s: Pricing complete — %d/%d priced, total: $%.2f",
        request_id, priced_count, len(priced_materials), total_cost,
    )

    # Step 5: Save to database
    try:
        estimate = save_estimate(
            image_filename=filename,
            scene_description=analysis.get("scene_description", ""),
            limitations=analysis.get("limitations", ""),
            materials=priced_materials,
        )
        estimate_id = estimate.id
        logger.info("%s: Estimate saved as ID %d", request_id, estimate_id)
    except Exception as e:
        estimate_id = None
        logger.error("%s: Failed to save estimate: %s", request_id, str(e))

    # Step 6: Return results
    response = {
        "id": estimate_id,
        "cost_basis": "materials_only",
        "estimate_status": "partial" if priced_count < len(priced_materials) else "preliminary",
        "unpriced_count": len(priced_materials) - priced_count,
        "scene_description": analysis.get("scene_description", ""),
        "limitations": analysis.get("limitations", ""),
        "materials": priced_materials,
        "total_cost": round(total_cost, 2),
        "material_count": len(priced_materials),
        "priced_count": priced_count,
    }

    logger.info("%s: Request complete", request_id)
    return JSONResponse(status_code=200, content=response)


@app.get("/api/estimates")
async def list_estimates(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    """List past estimates, newest first."""
    estimates = get_estimates(limit=limit, offset=offset)
    return JSONResponse(status_code=200, content={"estimates": estimates})


@app.get("/api/estimates/{estimate_id}")
async def get_estimate(estimate_id: int):
    """Retrieve a single estimate by ID."""
    estimate = get_estimate_by_id(estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return JSONResponse(status_code=200, content=estimate)


@app.get("/")
async def root():
    """Redirect to the upload page."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")
