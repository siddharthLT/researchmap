from collections import defaultdict

from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render

from .models import Company


def map_view(request):
    return render(request, "companymap/map.html")


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
    city_groups = defaultdict(list)
    for company in companies.exclude(city="", state_code=""):
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

    return JsonResponse(
        {
            "states": state_counts,
            "cities": sorted(cities, key=lambda item: (item["state_code"], item["city"])),
            "companies": [company.as_map_dict() for company in companies],
        }
    )

# Create your views here.
