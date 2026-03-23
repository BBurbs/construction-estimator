import asyncio
import logging

import httpx

from app.utils import retry_with_backoff

logger = logging.getLogger(__name__)


class PricingNotFoundError(Exception):
    """No pricing data found in RSMeans for this item."""
    pass


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
            "unit": top.get("unit", "ea"),
            "description": top.get("description", search_term),
            "rsmeans_code": top.get("lineNumber", top.get("code", "N/A")),
            "material_cost": float(top.get("materialCost", top.get("material_cost", 0))),
            "labor_cost": float(top.get("laborCost", top.get("labor_cost", 0))),
        }

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

            if not search_term:
                entry["cost_error"] = "No RSMeans search term available"
                return entry

            try:
                cost_info = await self.lookup_cost(
                    search_term=search_term,
                    division=material.get("rsmeans_division"),
                )
                entry["unit_cost"] = cost_info["unit_cost"]
                entry["material_cost"] = cost_info["material_cost"]
                entry["labor_cost"] = cost_info["labor_cost"]
                entry["rsmeans_description"] = cost_info["description"]
                entry["rsmeans_code"] = cost_info["rsmeans_code"]

                # Calculate total cost for this line item
                quantity = float(material.get("quantity", 0))
                entry["line_total"] = round(quantity * cost_info["unit_cost"], 2)

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
            except httpx.TimeoutException:
                entry["cost_error"] = "RSMeans API timeout"
                logger.error("RSMeans timeout for: %s", search_term)

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
