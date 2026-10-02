import asyncio
import logging
import math

import httpx

from app.utils import retry_with_backoff

logger = logging.getLogger(__name__)


class PricingNotFoundError(Exception):
    """No pricing data found in RSMeans for this item."""
    pass


def normalize_unit(unit: str) -> str:
    unit = str(unit).lower().strip().replace("²", "2").replace("³", "3")
    return {"sf": "sqft", "sq ft": "sqft", "ft2": "sqft", "lf": "lf",
            "linear feet": "lf", "ft": "lf", "each": "ea", "cy": "cuyd",
            "cu yd": "cuyd", "lbs": "lb"}.get(unit, unit)


class RSMeansClient:
    """Async client for Gordian RSMeans Data API."""

    def __init__(self, api_key: str, base_url: str = "https://api.gordian.com/v1"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )

    async def close(self):
        await self.client.aclose()

    @retry_with_backoff(
        max_retries=2,
        base_delay=1.0,
        exceptions=(httpx.TimeoutException, httpx.HTTPStatusError),
    )
    async def lookup_cost(self, search_term: str, division: str = None) -> dict:
        """Look up unit cost from RSMeans API.

        Args:
            search_term: Material search term (e.g., "lumber 2x4")
            division: Optional CSI division code to narrow search

        Returns:
            Dict with unit_cost, unit, description, rsmeans_code.

        Raises:
            PricingNotFoundError: No results for this search
            httpx.TimeoutException: After retries
            httpx.HTTPStatusError: Auth/server errors after retries
        """
        params = {"q": search_term, "limit": 5}
        if division:
            params["division"] = division

        logger.info("RSMeans lookup: '%s' (division: %s)", search_term, division or "any")

        response = await self.client.get(
            f"{self.base_url}/costdata/search",
            params=params,
        )
        response.raise_for_status()

        data = response.json()
        results = data.get("results", data.get("data", []))

        if not results:
            raise PricingNotFoundError(
                f"No RSMeans pricing found for: '{search_term}'"
            )

        # Take the first (most relevant) result
        top = results[0]
        cost_info = {
            "unit_cost": float(top.get("unitCost", top.get("unit_cost", top.get("totalCost", 0)))),
            "unit": top.get("unit", ""),
            "description": top.get("description", search_term),
            "rsmeans_code": top.get("lineNumber", top.get("code", "N/A")),
            "material_cost": top.get("materialCost", top.get("material_cost")),
            "labor_cost": float(top.get("laborCost", top.get("labor_cost", 0))),
        }

        value = cost_info["material_cost"]
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise PricingNotFoundError("Material-only price is unavailable")
        if not math.isfinite(value) or value < 0 or not cost_info["unit"]:
            raise PricingNotFoundError("Invalid material price or missing pricing unit")
        cost_info["material_cost"] = value

        logger.info(
            "RSMeans result: '%s' → $%.2f/%s (code: %s)",
            search_term, cost_info["unit_cost"], cost_info["unit"], cost_info["rsmeans_code"],
        )

        return cost_info

    async def lookup_multiple(self, materials: list[dict]) -> list[dict]:
        """Look up costs for multiple materials concurrently.

        Each material dict should have 'rsmeans_search_term' and optionally
        'rsmeans_division'. Items without these fields are skipped.

        Returns enriched list with cost data added to each item.
        """

        async def _lookup_one(material: dict) -> dict:
            entry = {**material}
            search_term = material.get("rsmeans_search_term")

            if material.get("match_warning"):
                entry["cost_error"] = "Ambiguous material match; verify the specification before pricing"
                return entry

            if not search_term:
                entry["cost_error"] = "No RSMeans search term available"
                return entry

            try:
                cost_info = await self.lookup_cost(
                    search_term=search_term,
                    division=material.get("rsmeans_division"),
                )
                entry["pricing_unit"] = cost_info["unit"]
                if not material.get("unit") or normalize_unit(material["unit"]) != normalize_unit(cost_info["unit"]):
                    entry["cost_error"] = f"Unit mismatch: quantity uses {material.get('unit', 'unknown')}, price uses {cost_info['unit']}. Measurements or conversion required."
                    return entry
                entry["unit_cost"] = cost_info["material_cost"]
                entry["cost_basis"] = "materials_only"
                quantity = material.get("quantity")
                if quantity is None:
                    entry["cost_error"] = "Quantity requires a measurement or visible count"
                    return entry
                quantity = float(quantity)
                if not math.isfinite(quantity) or quantity < 0:
                    entry["cost_error"] = "Invalid quantity"
                    return entry
                entry["unit_cost"] = cost_info["material_cost"]
                entry["cost_basis"] = "materials_only"
                entry["material_cost"] = cost_info["material_cost"]
                entry["labor_cost"] = cost_info["labor_cost"]
                entry["rsmeans_description"] = cost_info["description"]
                entry["rsmeans_code"] = cost_info["rsmeans_code"]

                # Calculate total cost for this line item
                quantity = float(material.get("quantity", 0))
                entry["line_total"] = round(quantity * entry["unit_cost"], 2)

            except PricingNotFoundError:
                entry["cost_error"] = f"No pricing found for '{search_term}'"
                logger.warning("No pricing for: %s", search_term)
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403):
                    entry["cost_error"] = "RSMeans API authentication failed"
                    logger.error("RSMeans auth error: %s", e)
                else:
                    entry["cost_error"] = f"RSMeans API error: {e.response.status_code}"
                    logger.error("RSMeans API error: %s", e)
            except (TypeError, ValueError, KeyError):
                entry["cost_error"] = "Invalid pricing response or quantity"
            except httpx.RequestError:
                entry["cost_error"] = "Pricing service unavailable"

            return entry

        # Run all lookups concurrently
        results = await asyncio.gather(
            *[_lookup_one(m) for m in materials],
            return_exceptions=False,
        )

        priced = sum(1 for r in results if "unit_cost" in r)
        total = sum(r.get("line_total", 0) for r in results)
        logger.info(
            "RSMeans pricing complete: %d/%d priced, estimated total: $%.2f",
            priced, len(results), total,
        )

        return list(results)
