import logging
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class MaterialNotFoundError(Exception):
    """No RSMeans match found for material."""
    pass


class AmbiguousMatchError(Exception):
    """Multiple equally good RSMeans matches found."""

    def __init__(self, message: str, best_match: dict):
        super().__init__(message)
        self.best_match = best_match


# Common construction materials mapped to RSMeans division codes and search terms.
# This table covers the most frequently identified materials from site photos.
# Format: keyword → (rsmeans_division, rsmeans_search_term, default_unit)
MATERIAL_CATALOG = {
    # Division 03 — Concrete
    "concrete": ("03", "concrete ready mix", "cuyd"),
    "concrete block": ("04", "concrete block", "ea"),
    "cmu": ("04", "concrete masonry unit", "ea"),
    "rebar": ("03", "reinforcing steel rebar", "lb"),
    "reinforcing bar": ("03", "reinforcing steel rebar", "lb"),
    "wire mesh": ("03", "welded wire fabric", "sqft"),
    "form": ("03", "concrete formwork", "sqft"),

    # Division 04 — Masonry
    "brick": ("04", "brick common", "ea"),
    "mortar": ("04", "mortar type S", "cuft"),
    "stone veneer": ("04", "stone veneer", "sqft"),

    # Division 05 — Metals
    "steel beam": ("05", "structural steel beam", "lb"),
    "steel column": ("05", "structural steel column", "lb"),
    "steel joist": ("05", "steel joist", "lf"),
    "metal stud": ("05", "metal stud framing", "lf"),
    "steel decking": ("05", "steel floor decking", "sqft"),
    "angle iron": ("05", "steel angle", "lf"),

    # Division 06 — Wood/Plastics
    "2x4": ("06", "lumber 2x4", "lf"),
    "2x6": ("06", "lumber 2x6", "lf"),
    "2x8": ("06", "lumber 2x8", "lf"),
    "2x10": ("06", "lumber 2x10", "lf"),
    "2x12": ("06", "lumber 2x12", "lf"),
    "4x4": ("06", "lumber 4x4 post", "lf"),
    "plywood": ("06", "plywood sheathing", "sqft"),
    "osb": ("06", "OSB sheathing", "sqft"),
    "lumber": ("06", "lumber framing", "lf"),
    "truss": ("06", "wood truss", "lf"),
    "joist": ("06", "wood joist", "lf"),
    "beam": ("06", "glulam beam", "lf"),
    "subfloor": ("06", "plywood subfloor", "sqft"),
    "sheathing": ("06", "wall sheathing", "sqft"),

    # Division 07 — Thermal/Moisture
    "shingle": ("07", "asphalt shingle roofing", "sqft"),
    "asphalt shingle": ("07", "asphalt shingle roofing", "sqft"),
    "metal roofing": ("07", "metal roofing panel", "sqft"),
    "roof membrane": ("07", "EPDM roofing membrane", "sqft"),
    "flashing": ("07", "roof flashing aluminum", "lf"),
    "insulation": ("07", "batt insulation fiberglass", "sqft"),
    "rigid insulation": ("07", "rigid foam insulation", "sqft"),
    "spray foam": ("07", "spray foam insulation", "sqft"),
    "house wrap": ("07", "house wrap vapor barrier", "sqft"),
    "tyvek": ("07", "house wrap vapor barrier", "sqft"),
    "siding": ("07", "vinyl siding", "sqft"),
    "vinyl siding": ("07", "vinyl siding", "sqft"),
    "stucco": ("07", "stucco exterior finish", "sqft"),
    "waterproofing": ("07", "waterproofing membrane", "sqft"),
    "tar paper": ("07", "asphalt felt underlayment", "sqft"),
    "ice and water shield": ("07", "ice water shield membrane", "sqft"),

    # Division 08 — Openings
    "window": ("08", "vinyl window double hung", "ea"),
    "door": ("08", "interior door prehung", "ea"),
    "exterior door": ("08", "exterior door steel", "ea"),
    "garage door": ("08", "garage door overhead", "ea"),
    "sliding door": ("08", "sliding glass door", "ea"),
    "skylight": ("08", "skylight fixed", "ea"),

    # Division 09 — Finishes
    "drywall": ("09", "gypsum drywall 1/2 inch", "sqft"),
    "gypsum board": ("09", "gypsum drywall 1/2 inch", "sqft"),
    "sheetrock": ("09", "gypsum drywall 1/2 inch", "sqft"),
    "tile": ("09", "ceramic tile floor", "sqft"),
    "ceramic tile": ("09", "ceramic tile floor", "sqft"),
    "carpet": ("09", "carpet broadloom", "sqft"),
    "hardwood floor": ("09", "hardwood flooring oak", "sqft"),
    "laminate": ("09", "laminate flooring", "sqft"),
    "vinyl flooring": ("09", "vinyl flooring sheet", "sqft"),
    "lvp": ("09", "luxury vinyl plank flooring", "sqft"),
    "paint": ("09", "interior paint latex", "sqft"),
    "primer": ("09", "primer sealer", "sqft"),
    "joint compound": ("09", "joint compound drywall", "sqft"),
    "ceiling tile": ("09", "acoustic ceiling tile", "sqft"),
    "drop ceiling": ("09", "suspended ceiling grid", "sqft"),

    # Division 15/22 — Plumbing
    "copper pipe": ("22", "copper pipe type L", "lf"),
    "pvc pipe": ("22", "PVC pipe schedule 40", "lf"),
    "pex": ("22", "PEX tubing", "lf"),
    "pipe": ("22", "pipe", "lf"),
    "fitting": ("22", "pipe fitting", "ea"),
    "water heater": ("22", "water heater gas", "ea"),
    "toilet": ("22", "toilet water closet", "ea"),
    "sink": ("22", "lavatory sink", "ea"),
    "faucet": ("22", "faucet kitchen", "ea"),
    "bathtub": ("22", "bathtub fiberglass", "ea"),

    # Division 16/26 — Electrical
    "wire": ("26", "electrical wire romex 12/2", "lf"),
    "romex": ("26", "electrical wire romex 12/2", "lf"),
    "conduit": ("26", "EMT conduit", "lf"),
    "outlet": ("26", "receptacle outlet duplex", "ea"),
    "receptacle": ("26", "receptacle outlet duplex", "ea"),
    "switch": ("26", "light switch single pole", "ea"),
    "panel": ("26", "electrical panel breaker", "ea"),
    "breaker": ("26", "circuit breaker", "ea"),
    "light fixture": ("26", "light fixture LED", "ea"),
    "junction box": ("26", "junction box", "ea"),

    # Division 31/32 — Sitework
    "gravel": ("31", "gravel crushed stone", "cuyd"),
    "sand": ("31", "sand fill", "cuyd"),
    "topsoil": ("31", "topsoil", "cuyd"),
    "asphalt": ("32", "asphalt paving", "sqft"),
    "concrete slab": ("03", "concrete slab on grade", "sqft"),
    "foundation": ("03", "concrete foundation wall", "lf"),
}


def _normalize(name: str) -> str:
    """Normalize material name for matching."""
    return name.lower().strip().replace("-", " ").replace("\"", "").replace("'", "")


def _similarity(a: str, b: str) -> float:
    """Compute string similarity ratio."""
    return SequenceMatcher(None, a, b).ratio()


def match_material(material_name: str) -> dict:
    """Match a material name from Claude Vision to an RSMeans catalog entry.

    Returns dict with:
        - matched_name: the catalog key that matched
        - rsmeans_division: CSI division code
        - rsmeans_search_term: term to search RSMeans API
        - default_unit: standard unit of measure
        - match_confidence: "exact", "fuzzy", or "ambiguous"

    Raises:
        MaterialNotFoundError: No match found
        AmbiguousMatchError: Multiple equally good matches (includes best_match)
    """
    normalized = _normalize(material_name)

    # Pass 1: Exact match on catalog keys
    if normalized in MATERIAL_CATALOG:
        division, search_term, unit = MATERIAL_CATALOG[normalized]
        logger.info("Exact match: '%s' → '%s'", material_name, normalized)
        return {
            "matched_name": normalized,
            "rsmeans_division": division,
            "rsmeans_search_term": search_term,
            "default_unit": unit,
            "match_confidence": "exact",
        }

    # Pass 2: Check if any catalog key is contained in the input (or vice versa)
    contained_matches = []
    for key, (division, search_term, unit) in MATERIAL_CATALOG.items():
        if key in normalized or normalized in key:
            # Score by how much of the input the key covers (longer key = better match)
            coverage = len(key) / max(len(normalized), 1)
            contained_matches.append((key, division, search_term, unit, 0.7 + 0.3 * coverage))

    if contained_matches:
        # Sort by score descending, pick best
        contained_matches.sort(key=lambda x: x[4], reverse=True)
        best = contained_matches[0]
        # If clear winner (>0.05 gap to second), return it
        if len(contained_matches) == 1 or (contained_matches[0][4] - contained_matches[1][4]) >= 0.05:
            key, division, search_term, unit, _ = best
            logger.info("Substring match: '%s' → '%s'", material_name, key)
            return {
                "matched_name": key,
                "rsmeans_division": division,
                "rsmeans_search_term": search_term,
                "default_unit": unit,
                "match_confidence": "fuzzy",
            }

    # Pass 3: Fuzzy match using sequence similarity
    scored = []
    for key, (division, search_term, unit) in MATERIAL_CATALOG.items():
        score = _similarity(normalized, key)
        # Also check similarity against the search term
        term_score = _similarity(normalized, search_term.lower())
        best_score = max(score, term_score)
        if best_score > 0.55:
            scored.append((key, division, search_term, unit, best_score))

    # Combine with contained matches (if pass 2 was ambiguous)
    all_matches = contained_matches + scored
    # Deduplicate by key name, keeping highest score
    seen = {}
    for item in all_matches:
        key = item[0]
        if key not in seen or item[4] > seen[key][4]:
            seen[key] = item
    all_matches = sorted(seen.values(), key=lambda x: x[4], reverse=True)

    if not all_matches:
        raise MaterialNotFoundError(
            f"No RSMeans match found for material: '{material_name}'"
        )

    best = all_matches[0]
    best_result = {
        "matched_name": best[0],
        "rsmeans_division": best[1],
        "rsmeans_search_term": best[2],
        "default_unit": best[3],
        "match_confidence": "fuzzy",
    }

    # Check for ambiguity — top two scores within 0.05 of each other
    if len(all_matches) >= 2 and (all_matches[0][4] - all_matches[1][4]) < 0.05:
        logger.warning(
            "Ambiguous match for '%s': '%s' (%.2f) vs '%s' (%.2f)",
            material_name, all_matches[0][0], all_matches[0][4],
            all_matches[1][0], all_matches[1][4],
        )
        raise AmbiguousMatchError(
            f"Ambiguous match for '{material_name}': could be '{all_matches[0][0]}' or '{all_matches[1][0]}'",
            best_match=best_result,
        )

    logger.info(
        "Fuzzy match: '%s' → '%s' (score: %.2f)",
        material_name, best[0], best[4],
    )
    return best_result


def match_materials(materials: list[dict]) -> list[dict]:
    """Match a list of materials from Vision API to RSMeans entries.

    Each material dict should have at least 'name'.
    Returns enriched list with RSMeans match info added to each item.
    Items that fail to match get a 'match_error' field instead.
    """
    results = []
    for material in materials:
        name = material.get("name", "unknown")
        entry = {**material}

        try:
            match = match_material(name)
            entry.update(match)
        except AmbiguousMatchError as e:
            entry.update(e.best_match)
            entry["match_warning"] = str(e)
            logger.warning("Ambiguous match for '%s', using best guess", name)
        except MaterialNotFoundError:
            entry["match_error"] = f"No RSMeans match found for '{name}'"
            logger.warning("No match found for '%s'", name)

        results.append(entry)

    matched = sum(1 for r in results if "rsmeans_search_term" in r)
    logger.info("Matched %d/%d materials to RSMeans codes", matched, len(results))

    return results
