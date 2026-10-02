# Construction material estimator

Upload a site photo to identify visible materials and obtain a preliminary material-only subtotal. This is not a complete project bid.

## Run locally

Use Python 3.10 or later. Install `requirements.txt`, copy `.env.example` to `.env`, and supply your Anthropic and licensed RSMeans credentials. Set `ANTHROPIC_MODEL` to a vision-capable model available to your account. Start from the repository root:

```
uvicorn app.main:app --reload
```

Open http://localhost:8000. Run `python -m pytest -q` for the mocked regression suite.

## Estimate behavior

- Quantities without visible counts or known dimensions should be left blank by the AI. Review the notes and enter measured quantities in the interface.
- Quantity and pricing units must agree. Equivalent abbreviations are accepted; physical conversions are not guessed.
- Only an explicit material cost from the pricing provider is used. Installed totals are not substituted when material pricing is absent.
- Ambiguous catalog matches are excluded until the specification is verified. The current interface does not resolve these matches.
- Missing measurements and unpriced items are excluded from the subtotal, not valued at zero. Labor, equipment, tax, delivery, waste, overhead and profit are excluded.
- Quantity edits recalculate compatible prices in the browser only. They are not saved to estimate history.
- Photos are oriented, resized, converted to JPEG and stripped of EXIF before storage and analysis.

## Integration limits

The existing RSMeans adapter expects `/costdata/search` and fields including `materialCost`, `unit`, `description` and `lineNumber`. This contract has only been exercised with mocked responses. Confirm the endpoint, authentication, field names, price currency, data date and regional basis against your licensed Gordian service before relying on pricing. Search results still use the provider's first candidate and require specification review.

Existing saved estimates retain their original cost calculations. New estimates use material-only costs. Do not compare old totals with new totals without recalculating them.

This prototype has no user authentication or per-user history isolation. Keep it private until those are implemented. Live AI and pricing integrations have not been validated by the regression suite.
