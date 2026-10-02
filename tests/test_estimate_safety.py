import pytest
from unittest.mock import AsyncMock
from pydantic import ValidationError
from app.vision import VisionAnalysis
from app.rsmeans import RSMeansClient

@pytest.mark.parametrize('quantity', [-1, float('nan'), float('inf')])
def test_invalid_vision_quantities(quantity):
    with pytest.raises(ValidationError):
        VisionAnalysis.model_validate({'materials': [{'name': 'drywall', 'quantity': quantity, 'unit': 'sqft', 'confidence': 'low'}]})

def test_missing_measurement_is_allowed():
    result = VisionAnalysis.model_validate({'materials': [{'name': 'drywall', 'quantity': None, 'unit': 'sqft', 'confidence': 'low'}]})
    assert result.materials[0].quantity is None

@pytest.mark.asyncio
@pytest.mark.parametrize('unit, quantity, warning, expected', [
    ('sqft', 10, None, None),
    ('lf', None, None, None),
    ('lf', 10, 'ambiguous', None),
    ('linear feet', 10, None, 9.5),
])
async def test_pricing_requires_compatible_measured_quantity(unit, quantity, warning, expected):
    client = RSMeansClient('test')
    client.lookup_cost = AsyncMock(return_value={'unit': 'lf', 'unit_cost': 1.85, 'material_cost': .95, 'labor_cost': .9, 'description': 'lumber', 'rsmeans_code': 'test'})
    try:
        result = (await client.lookup_multiple([{'name': 'lumber', 'unit': unit, 'quantity': quantity, 'rsmeans_search_term': 'lumber', 'match_warning': warning}]))[0]
        assert result.get('line_total') == expected
        if expected is None:
            assert 'cost_error' in result
        else:
            assert result['cost_basis'] == 'materials_only'
    finally:
        await client.close()
