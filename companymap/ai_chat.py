import json
import logging
from math import radians, sin, cos, sqrt, atan2

from openai import OpenAI

from .models import Company

logger = logging.getLogger(__name__)

MODEL = "gpt-4o"
MAX_TOOL_ROUNDS = 6
DEFAULT_RADIUS_KM = 10.0
DEFAULT_RESULT_LIMIT = 40
MAX_RESULT_LIMIT = 100

SYSTEM_PROMPT = """You are a research assistant embedded in a company map application. \
You help the user find companies in the database by location, distance from another \
company, revenue, funding status, industry, and employee count.

Use the search_companies tool to look up companies — you may call it several times to \
narrow down or cross-check results (for example: first resolve a company's location \
with a broad search, then search again with a distance filter). Only reference company \
IDs that were actually returned by search_companies.

When you're ready to answer, call present_answer exactly once with a concise, specific \
natural-language message (mention concrete numbers and names, not just counts) and the \
IDs of the companies you're referencing, ordered by relevance. If nothing matches, say \
so plainly in the message and pass an empty company_ids list. Never call present_answer \
before you have searched at least once."""

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_companies",
        "description": (
            "Search the company database. All filters are optional and combine with AND. "
            "Use near_company_name + radius_km to find companies within a distance of a "
            "named company (the tool resolves the name and computes real distances)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name_contains": {"type": "string", "description": "Substring match on company name."},
                "state_code": {"type": "string", "description": "Two-letter US state code, e.g. NY."},
                "city": {"type": "string", "description": "Substring match on city name."},
                "industry_contains": {"type": "string", "description": "Substring match on industry."},
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
                "employee_count": company.employee_count,
                "annual_revenue": company.annual_revenue,
                "has_funding": bool(company.funding_data),
                "funding_data": company.funding_data[:200],
                "distance_km": distance_by_id.get(company.id),
            }
            for company in companies
        ],
    }


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

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in (history or [])[-10:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    known_ids = set()

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

        present_call = next(
            (c for c in tool_calls if c.function.name == "present_answer"), None
        )
        if present_call:
            args = json.loads(present_call.function.arguments)
            company_ids = [cid for cid in args.get("company_ids", []) if cid in known_ids]
            return {"reply": args.get("message", ""), "company_ids": company_ids}

        if not tool_calls:
            text = assistant_message.content or ""
            return {"reply": text or "I couldn't find an answer.", "company_ids": []}

        messages.append(_assistant_message_dict(assistant_message))

        for call in tool_calls:
            if call.function.name == "search_companies":
                args = json.loads(call.function.arguments or "{}")
                result = _search_companies(**args)
            else:
                result = {"error": f"Unknown tool: {call.function.name}"}
            if "companies" in result:
                known_ids.update(c["id"] for c in result["companies"])
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result),
            })

    logger.warning("AI chat exceeded max tool rounds without a final answer")
    return {
        "reply": "I wasn't able to finish that search in time — try narrowing your question.",
        "company_ids": [],
    }
