import json
import logging
from collections import defaultdict

from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from contactdb.models import Person
from conferences.models import ConferenceCompany

from .ai_chat import run_chat
from .models import Company

logger = logging.getLogger(__name__)


def map_view(request):
    return render(request, "companymap/map.html")


@xframe_options_sameorigin
def company_pin_map(request, company_id):
    company = get_object_or_404(
        Company.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True),
        id=company_id,
    )
    return render(request, "companymap/company_pin.html", {"company": company})


@require_POST
def chat_api(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    message = (payload.get("message") or "").strip()
    if not message:
        return JsonResponse({"error": "Message is required."}, status=400)

    history = payload.get("history") or []

    try:
        result = run_chat(message, history)
    except Exception:
        logger.exception("AI chat request failed")
        return JsonResponse({"error": "The assistant is unavailable right now."}, status=502)

    return JsonResponse(result)


def company_map_data(request):
    companies = Company.objects.prefetch_related("decision_makers").filter(
        latitude__isnull=False,
        longitude__isnull=False,
    )

    state_code = request.GET.get("state")
    city = request.GET.get("city")
    if state_code:
        companies = companies.filter(state_code__iexact=state_code)
    if city:
        companies = companies.filter(city__iexact=city)

    state_counts = list(
        companies.values("state_code", "region")
        .exclude(state_code="")
        .annotate(company_count=Count("id"))
        .order_by("state_code")
    )
    companies = list(companies)

    city_groups = defaultdict(list)
    for company in companies:
        if company.city and company.state_code:
            city_groups[(company.state_code, company.city)].append(company)

    cities = []
    for (code, city_name), group in city_groups.items():
        lat = sum(float(company.latitude) for company in group) / len(group)
        lng = sum(float(company.longitude) for company in group) / len(group)
        cities.append(
            {
                "state_code": code,
                "city": city_name,
                "company_count": len(group),
                "high_revenue_count": sum(1 for company in group if company.annual_revenue and company.annual_revenue >= 10_000_000),
                "latitude": lat,
                "longitude": lng,
            }
        )

    warm_connectors_by_company = defaultdict(set)
    for company_id, connectors in (
        Person.objects.exclude(prior_connections=[])
        .exclude(company__isnull=True)
        .values_list("company_id", "prior_connections")
    ):
        for connector in connectors:
            if connector:
                warm_connectors_by_company[company_id].add(connector)

    conferences_by_company = defaultdict(set)
    for company_id, conference_name in (
        ConferenceCompany.objects.exclude(company__isnull=True)
        .select_related("conference")
        .values_list("company_id", "conference__name")
    ):
        conferences_by_company[company_id].add(conference_name)

    companies_data = []
    for company in companies:
        data = company.as_map_dict()
        data["warm_connectors"] = sorted(warm_connectors_by_company.get(company.id, ()))
        data["has_warm_connection"] = bool(data["warm_connectors"])
        data["conferences"] = sorted(conferences_by_company.get(company.id, ()))
        data["has_conference"] = bool(data["conferences"])
        companies_data.append(data)

    return JsonResponse(
        {
            "states": state_counts,
            "cities": sorted(cities, key=lambda item: (item["state_code"], item["city"])),
            "companies": companies_data,
        }
    )

# Create your views here.
