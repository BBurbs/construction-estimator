import pytest

from app.matcher import match_material, match_materials, MaterialNotFoundError, AmbiguousMatchError


class TestMatchMaterial:
    def test_exact_match_2x4(self):
        result = match_material("2x4")
        assert result["matched_name"] == "2x4"
        assert result["rsmeans_division"] == "06"
        assert result["match_confidence"] == "exact"

    def test_exact_match_drywall(self):
        result = match_material("drywall")
        assert result["matched_name"] == "drywall"
        assert result["rsmeans_division"] == "09"

    def test_exact_match_case_insensitive(self):
        result = match_material("CONCRETE")
        assert result["matched_name"] == "concrete"

    def test_exact_match_strips_whitespace(self):
        result = match_material("  plywood  ")
        assert result["matched_name"] == "plywood"

    def test_substring_match(self):
        result = match_material("asphalt shingle roofing")
        assert result["rsmeans_division"] == "07"
        assert result["match_confidence"] in ("exact", "fuzzy")
        assert result["matched_name"] == "asphalt shingle"

    def test_fuzzy_match_close_name(self):
        result = match_material("copper piping")
        assert result["matched_name"] == "copper pipe"
        assert result["rsmeans_division"] == "22"

    def test_no_match_raises(self):
        with pytest.raises(MaterialNotFoundError):
            match_material("zqxjkvwp utterly unknown thing")

    def test_no_match_gibberish(self):
        with pytest.raises(MaterialNotFoundError):
            match_material("xyzzyabcde12345")

    def test_common_materials(self):
        """Verify common construction materials all match."""
        materials = ["concrete", "brick", "lumber", "drywall", "shingle",
                     "insulation", "plywood", "window", "door", "pipe"]
        for name in materials:
            result = match_material(name)
            assert "rsmeans_search_term" in result, f"Failed to match: {name}"


class TestMatchMaterials:
    def test_mixed_results(self):
        materials = [
            {"name": "2x4 lumber", "quantity": 50, "unit": "lf"},
            {"name": "zqxjkvwp unknown thing", "quantity": 10, "unit": "ea"},
            {"name": "drywall", "quantity": 200, "unit": "sqft"},
        ]
        results = match_materials(materials)
        assert len(results) == 3

        # First should match (contains "2x4" and "lumber")
        assert "rsmeans_search_term" in results[0]
        # Second should have error (truly unknown material)
        assert "match_error" in results[1]
        # Third should match
        assert "rsmeans_search_term" in results[2]

    def test_preserves_original_fields(self):
        materials = [{"name": "concrete", "quantity": 5, "unit": "cuyd", "confidence": "high"}]
        results = match_materials(materials)
        assert results[0]["quantity"] == 5
        assert results[0]["confidence"] == "high"

    def test_empty_list(self):
        results = match_materials([])
        assert results == []
