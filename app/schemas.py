from pydantic import BaseModel


class MaterialItem(BaseModel):
    name: str
    quantity: float | None
    unit: str
    confidence: str  # high, medium, low
    notes: str = ""
    matched_name: str | None = None
    rsmeans_division: str | None = None
    rsmeans_search_term: str | None = None
    rsmeans_code: str | None = None
    rsmeans_description: str | None = None
    match_confidence: str | None = None  # exact, fuzzy, ambiguous
    match_warning: str | None = None
    match_error: str | None = None
    unit_cost: float | None = None
    material_cost: float | None = None
    labor_cost: float | None = None
    line_total: float | None = None
    cost_error: str | None = None


class EstimateResponse(BaseModel):
    id: int | None = None
    scene_description: str
    limitations: str
    materials: list[MaterialItem]
    total_cost: float
    material_count: int
    priced_count: int


class EstimateHistoryItem(BaseModel):
    id: int
    created_at: str | None
    image_filename: str
    scene_description: str | None
    total_cost: float
    material_count: int
    priced_count: int


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
