import json
import logging
import re
from math import radians, sin, cos, sqrt, atan2

from django.db.models import Q
from openai import OpenAI

from .models import Company

logger = logging.getLogger(__name__)

MODEL = "gpt-4o"
MAX_TOOL_ROUNDS = 6
DEFAULT_RADIUS_KM = 10.0
DEFAULT_RESULT_LIMIT = 40
MAX_RESULT_LIMIT = 100

KEYWORD_FIELDS = ("industry", "product_category", "sub_type", "segment", "notes")


def _distinct_industries():
    return sorted(
        value for value in Company.objects.exclude(industry="")
        .values_list("industry", flat=True).distinct()
    )


def _build_system_prompt():
    industries = ", ".join(_distinct_industries())
    return f"""You are a research assistant embedded in a company map application. \
You help the user find companies in the database by location, distance from another \
company, revenue, funding status, industry, modality/technology focus, and employee count.

Field semantics — read carefully, these are two different levels of detail:
- `industry` is a coarse category. The complete set of values in this database is: \
{industries}. It does NOT capture therapeutic modality, technology platform, or business \
model (e.g. it will never say "cell therapy" or "CDMO" or "biologics").
- `product_category`, `sub_type`, and `segment` (plus free-text `notes`) hold the specific \
detail: modality (e.g. "Biologics / Large Molecule", "mRNA", "Antibody reagents"), business \
model (e.g. "CRO", "CDMO", "Drug Developer"), and technology platform. When the user asks \
about modality, therapeutic area, technology, or "what kind of company is X", search with \
the `keywords` filter and read these fields from the results — do NOT infer or guess from \
`industry` alone, and do NOT answer a modality question using only the `industry` field.

Use the search_companies tool to look up companies — you may call it several times to \
narrow down or cross-check results (for example: first resolve a company's location \
with a broad search, then search again with a distance filter, or run separate keyword \
searches for each modality the user asks about). Only reference company IDs that were \
actually returned by search_companies.

When you're ready to answer, call present_answer exactly once with a concise, specific \
natural-language message (mention concrete numbers, names, and — when relevant — the \
actual product_category/sub_type/segment values you saw, not generic category labels). \
company_ids is not optional: every company named in your message MUST have its ID in \
company_ids, in the same order they're mentioned — this is what makes them clickable on \
the map, so never send a name without its ID. If nothing matches, say so plainly in the \
message and pass an empty company_ids list. Never call present_answer before you have \
searched at least once in THIS turn — IDs from an earlier turn are not valid here, so \
re-run search_companies even if you already found these companies in a previous message."""


SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_companies",
        "description": (
            "Search the company database. All filters are optional and combine with AND "
            "(keywords within the list are OR'd together). Use near_company_name + "
            "radius_km to find companies within a distance of a named company (the tool "
            "resolves the name and computes real distances)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name_contains": {"type": "string", "description": "Substring match on company name."},
                "state_code": {"type": "string", "description": "Two-letter US state code, e.g. NY."},
                "city": {"type": "string", "description": "Substring match on city name."},
                "industry_contains": {
                    "type": "string",
                    "description": "Exact-ish substring match on the coarse industry field only.",
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Free-text terms to search for modality, technology, business model, "
                        "or focus area (e.g. 'cell therapy', 'gene therapy', 'CDMO', 'mRNA', "
                        "'biologics', 'small molecule'). Matches if ANY term appears in "
                        "industry, product_category, sub_type, segment, or the company "
                        "description. This is the right filter for anything more specific "
                        "than the coarse industry list."
                    ),
                },
                "min_revenue": {"type": "number", "description": "Minimum annual revenue in USD."},
                "max_revenue": {"type": "number", "description": "Maximum annual revenue in USD."},
                "has_funding": {"type": "boolean", "description": "Only companies with recorded funding data."},
                "min_employees": {"type": "number"},
                "max_employees": {"type": "number"},
                "near_company_name": {
                    "type": "string",
                    "description": "Name of a reference company to measure distance from.",
                },
                "radius_km": {
                    "type": "number",
                    "description": "Radius in kilometers from near_company_name. Defaults to 10.",
                },
                "limit": {
                    "type": "number",
                    "description": "Max results to return. Defaults to 40, capped at 100.",
                },
            },
            "additionalProperties": False,
        },
    },
}

PRESENT_ANSWER_TOOL = {
    "type": "function",
    "function": {
        "name": "present_answer",
        "description": (
            "Deliver your final answer to the user. Call this exactly once, after you have "
            "finished searching."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Natural language answer for the user."},
                "company_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "IDs of companies referenced in the message, most relevant first.",
                },
            },
            "required": ["message", "company_ids"],
            "additionalProperties": False,
        },
    },
}


def _haversine_km(lat1, lon1, lat2, lon2):
    radius_earth_km = 6371.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlambda / 2) ** 2
    return 2 * radius_earth_km * atan2(sqrt(a), sqrt(1 - a))


def _search_companies(
    name_contains=None,
    state_code=None,
    city=None,
    industry_contains=None,
    keywords=None,
    min_revenue=None,
    max_revenue=None,
    has_funding=None,
    min_employees=None,
    max_employees=None,
    near_company_name=None,
    radius_km=None,
    limit=None,
    **_ignored,
):
    qs = Company.objects.filter(latitude__isnull=False, longitude__isnull=False)
    if name_contains:
        qs = qs.filter(name__icontains=name_contains)
    if state_code:
        qs = qs.filter(state_code__iexact=state_code)
    if city:
        qs = qs.filter(city__icontains=city)
    if industry_contains:
        qs = qs.filter(industry__icontains=industry_contains)
    if keywords:
        keyword_filter = Q()
        for term in keywords:
            if not term:
                continue
            for field in KEYWORD_FIELDS:
                keyword_filter |= Q(**{f"{field}__icontains": term})
        qs = qs.filter(keyword_filter)
    if min_revenue is not None:
        qs = qs.filter(annual_revenue__gte=min_revenue)
    if max_revenue is not None:
        qs = qs.filter(annual_revenue__lte=max_revenue)
    if has_funding:
        qs = qs.exclude(funding_data="")
    if min_employees is not None:
        qs = qs.filter(employee_count__gte=min_employees)
    if max_employees is not None:
        qs = qs.filter(employee_count__lte=max_employees)

    companies = list(qs)
    distance_by_id = {}

    if near_company_name:
        origin = Company.objects.filter(
            name__icontains=near_company_name,
            latitude__isnull=False,
            longitude__isnull=False,
        ).first()
        if origin is None:
            return {
                "error": (
                    f"No company with coordinates found matching '{near_company_name}'. "
                    "Try a different spelling, or drop this filter."
                )
            }
        radius = float(radius_km) if radius_km else DEFAULT_RADIUS_KM
        nearby = []
        for company in companies:
            if company.id == origin.id:
                continue
            distance = _haversine_km(
                float(origin.latitude), float(origin.longitude),
                float(company.latitude), float(company.longitude),
            )
            if distance <= radius:
                distance_by_id[company.id] = round(distance, 2)
                nearby.append(company)
        nearby.sort(key=lambda c: distance_by_id[c.id])
        companies = nearby

    result_limit = min(int(limit), MAX_RESULT_LIMIT) if limit else DEFAULT_RESULT_LIMIT
    companies = companies[:result_limit]

    return {
        "count": len(companies),
        "companies": [
            {
                "id": company.id,
                "name": company.name,
                "city": company.city,
                "state_code": company.state_code,
                "industry": company.industry,
                "product_category": company.product_category,
                "sub_type": company.sub_type,
                "segment": company.segment,
                "employee_count": company.employee_count,
                "annual_revenue": company.annual_revenue,
                "has_funding": bool(company.funding_data),
                "funding_data": company.funding_data[:200],
                "description": company.notes[:280],
                "distance_km": distance_by_id.get(company.id),
            }
            for company in companies
        ],
    }


def _match_company_names_in_text(text, id_to_name):
    """Fallback for when the model names companies in its reply but forgets to list
    their IDs in company_ids: find company names in the text (as whole words, to avoid
    false positives on short names), in the order they first appear."""
    if not text or not id_to_name:
        return []
    matches = []
    for company_id, name in id_to_name.items():
        if not name:
            continue
        match = re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE)
        if match:
            matches.append((match.start(), company_id))
    matches.sort(key=lambda pair: pair[0])
    seen = set()
    ordered_ids = []
    for _, company_id in matches:
        if company_id not in seen:
            seen.add(company_id)
            ordered_ids.append(company_id)
    return ordered_ids


def _resolve_reply(reply_text, model_company_ids, known_companies):
    """Turn a reply plus the model's claimed company_ids into a final, verified ID list —
    falling back to matching real company names in the text when the model's structured
    output is empty or wrong, so a reply that clearly names companies never surfaces with
    no clickable results."""
    company_ids = [cid for cid in (model_company_ids or []) if cid in known_companies]
    if not company_ids:
        company_ids = _match_company_names_in_text(reply_text, known_companies)
    if not company_ids:
        # The model didn't search this turn (or searched something unrelated) but the
        # reply still names real companies — match against the whole database instead
        # of showing no results at all.
        all_names = dict(Company.objects.values_list("id", "name"))
        company_ids = _match_company_names_in_text(reply_text, all_names)
    return company_ids


def _assistant_message_dict(message):
    msg = {"role": "assistant", "content": message.content}
    if message.tool_calls:
        msg["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            }
            for call in message.tool_calls
        ]
    return msg


def run_chat(message, history=None):
    client = OpenAI()

    messages = [{"role": "system", "content": _build_system_prompt()}]
    for turn in (history or [])[-10:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    known_companies = {}  # id -> name, accumulated from every search this turn

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=[SEARCH_TOOL, PRESENT_ANSWER_TOOL],
            tool_choice="auto",
        )

        choice = response.choices[0]
        assistant_message = choice.message
        tool_calls = assistant_message.tool_calls or []

        if not tool_calls:
            text = assistant_message.content or ""
            if not text:
                return {"reply": "I couldn't find an answer.", "company_ids": []}
            return {"reply": text, "company_ids": _resolve_reply(text, [], known_companies)}

        # Run every search_companies call first — even if the model also called
        # present_answer in the same turn — so known_companies is fully populated
        # before we resolve the final answer's company_ids.
        present_call = None
        search_results = {}
        for call in tool_calls:
            if call.function.name == "present_answer":
                present_call = call
            elif call.function.name == "search_companies":
                args = json.loads(call.function.arguments or "{}")
                result = _search_companies(**args)
                if "companies" in result:
                    known_companies.update({c["id"]: c["name"] for c in result["companies"]})
                search_results[call.id] = result
            else:
                search_results[call.id] = {"error": f"Unknown tool: {call.function.name}"}

        if present_call:
            args = json.loads(present_call.function.arguments)
            reply_text = args.get("message", "")
            company_ids = _resolve_reply(reply_text, args.get("company_ids", []), known_companies)
            return {"reply": reply_text, "company_ids": company_ids}

        messages.append(_assistant_message_dict(assistant_message))
        for call_id, result in search_results.items():
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(result),
            })

    logger.warning("AI chat exceeded max tool rounds without a final answer")
    return {
        "reply": "I wasn't able to finish that search in time — try narrowing your question.",
        "company_ids": [],
    }
