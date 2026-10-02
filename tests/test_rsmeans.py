import json
import pytest
import httpx
import respx

from app.rsmeans import RSMeansClient, PricingNotFoundError


@pytest.fixture
def rsmeans_client():
    return RSMeansClient(api_key="test-key", base_url="https://api.gordian.com/v1")


class TestRSMeansLookup:
    @pytest.mark.asyncio
    @respx.mock
    async def test_successful_lookup(self, rsmeans_client, sample_rsmeans_response):
        respx.get("https://api.gordian.com/v1/costdata/search").mock(
            return_value=httpx.Response(200, json=sample_rsmeans_response)
        )

        result = await rsmeans_client.lookup_cost("lumber 2x4", division="06")
        assert result["unit_cost"] == 1.85
        assert result["material_cost"] == 0.95
        assert result["labor_cost"] == 0.90
        assert result["rsmeans_code"] == "06 11 10.10 0020"

        await rsmeans_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_no_results_raises(self, rsmeans_client):
        respx.get("https://api.gordian.com/v1/costdata/search").mock(
            return_value=httpx.Response(200, json={"results": []})
        )

        with pytest.raises(PricingNotFoundError):
            await rsmeans_client.lookup_cost("nonexistent material xyz")

        await rsmeans_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_auth_error(self, rsmeans_client):
        respx.get("https://api.gordian.com/v1/costdata/search").mock(
            return_value=httpx.Response(401, json={"error": "Unauthorized"})
        )

        with pytest.raises(httpx.HTTPStatusError):
            await rsmeans_client.lookup_cost("lumber 2x4")

        await rsmeans_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_timeout_retries(self, rsmeans_client):
        call_count = 0

        def side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.ReadTimeout("timeout")
            return httpx.Response(200, json={
                "results": [{"lineNumber": "test", "description": "test", "unit": "ea", "unitCost": 1.0, "materialCost": 0.5, "laborCost": 0.5}]
            })

        respx.get("https://api.gordian.com/v1/costdata/search").mock(side_effect=side_effect)

        result = await rsmeans_client.lookup_cost("lumber 2x4")
        assert result["unit_cost"] == 1.0
        assert call_count == 3

        await rsmeans_client.close()


class TestRSMeansLookupMultiple:
    @pytest.mark.asyncio
    @respx.mock
    async def test_concurrent_lookups(self, rsmeans_client):
        respx.get("https://api.gordian.com/v1/costdata/search").mock(
            return_value=httpx.Response(200, json={
                "results": [{"lineNumber": "test", "description": "test material", "unit": "lf", "unitCost": 2.00, "materialCost": 1.00, "laborCost": 1.00}]
            })
        )

        materials = [
            {"name": "2x4", "rsmeans_search_term": "lumber 2x4", "rsmeans_division": "06", "quantity": 50, "unit": "lf"},
            {"name": "drywall", "rsmeans_search_term": "gypsum drywall", "rsmeans_division": "09", "quantity": 200, "unit": "lf"},
        ]

        results = await rsmeans_client.lookup_multiple(materials)
        assert len(results) == 2
        assert results[0]["unit_cost"] == 1.00
        assert results[0]["line_total"] == 50.00  # 50 * material-only cost
        assert results[1]["line_total"] == 200.00  # 200 * material-only cost

        await rsmeans_client.close()

    @pytest.mark.asyncio
    async def test_skips_items_without_search_term(self, rsmeans_client):
        materials = [{"name": "unknown", "quantity": 10}]
        results = await rsmeans_client.lookup_multiple(materials)
        assert len(results) == 1
        assert "cost_error" in results[0]

        await rsmeans_client.close()
