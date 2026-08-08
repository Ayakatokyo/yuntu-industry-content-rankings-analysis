"""Build post-RPA facts for the TOP material combination report block."""


BRAND_RULES = (
    ("万益蓝/WONDERLAB", ("万益蓝", "wonderlab")),
    ("五个女博士", ("五个女博士",)),
    ("燕之屋", ("燕之屋",)),
)


def _positive_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def classify_brand(title):
    """Classify a title with an auditable business rule, never an RPA field."""
    text = str(title or "").casefold()
    matches = [
        brand
        for brand, keywords in BRAND_RULES
        if any(keyword.casefold() in text for keyword in keywords)
    ]
    if len(matches) == 1:
        return {"value": matches[0], "source": "title_rule"}
    if len(matches) > 1:
        return {"value": "歧义品牌", "source": "ambiguous"}
    return {"value": "未知品牌", "source": "unclassified"}


def select_top_materials(records, *, limit=30):
    """Return eligible material records in the documented exposure order."""
    eligible = [
        record
        for record in records
        if _positive_number(record.get("metrics", {}).get("show_cnt"))
    ]
    return sorted(
        eligible,
        key=lambda record: (
            -record["metrics"]["show_cnt"],
            record.get("rank", float("inf")),
            str(record.get("material_id", "")),
        ),
    )[:limit]
