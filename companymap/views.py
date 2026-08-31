import json
import logging
from collections import defaultdict

from django.core.paginator import Paginator
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from contactdb.models import Person
from conferences.models import ConferenceCompany

from .ai_chat import run_chat
from .models import Company, CompanyLinkedInPost

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


def social_room(request):
    posts = (
        CompanyLinkedInPost.objects
        .select_related("company")
        .exclude(company__isnull=True)
        .order_by("-post_date", "-created_at")
    )

    q = request.GET.get("q", "").strip()
    company_ids = [v for v in request.GET.getlist("company") if v]
    state_codes = [v for v in request.GET.getlist("state") if v]
    segments = [v for v in request.GET.getlist("segment") if v]
    categories = [v for v in request.GET.getlist("category") if v]
    view = request.GET.get("view", "").strip()

    if q:
        posts = posts.filter(Q(post_text__icontains=q) | Q(company__name__icontains=q))
    if company_ids:
        posts = posts.filter(company_id__in=company_ids)
    if state_codes:
        posts = posts.filter(company__state_code__in=state_codes)
    if segments:
        posts = posts.filter(company__segment__in=segments)
    if categories:
        posts = posts.filter(category__in=categories)

    saved_count = CompanyLinkedInPost.objects.filter(is_saved=True).count()
    if view == "saved":
        posts = posts.filter(is_saved=True)

    paginator = Paginator(posts, 30)
    page_number = request.GET.get("page") or 1
    page = paginator.get_page(page_number)

    page_range = [
        {"number": p, "is_ellipsis": p == Paginator.ELLIPSIS, "is_current": p == page.number}
        for p in paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)
    ]

    company_options = (
        Company.objects.filter(linkedin_posts__isnull=False)
        .distinct()
        .order_by("name")
        .values("id", "name")
    )
    state_options = (
        Company.objects.filter(linkedin_posts__isnull=False)
        .exclude(state_code="")
        .values_list("state_code", flat=True)
        .distinct()
        .order_by("state_code")
    )
    segment_options = (
        Company.objects.filter(linkedin_posts__isnull=False)
        .exclude(segment="")
        .values_list("segment", flat=True)
        .distinct()
        .order_by("segment")
    )
    category_options = CompanyLinkedInPost.Category.choices

    # Ticker: top 10 "real news" posts, ranked by how meaningful the signal is
    # to Lunartree first and recency second — funding/partnership/capability
    # news is the good stuff and often rare, so it must outrank the much more
    # common (and much less interesting) event-attendance and hiring posts
    # rather than just picking whatever is newest.
    ticker_posts = list(
        CompanyLinkedInPost.objects
        .select_related("company")
        .exclude(company__isnull=True)
        .filter(category__in=CompanyLinkedInPost.SIGNAL_CATEGORIES)
        .annotate(ticker_priority=Case(
            When(category=CompanyLinkedInPost.Category.NEW_FUNDING, then=Value(0)),
            When(category=CompanyLinkedInPost.Category.NEW_PARTNERSHIP, then=Value(0)),
            When(category=CompanyLinkedInPost.Category.CAPABILITY_EXPANSION, then=Value(0)),
            When(category=CompanyLinkedInPost.Category.RESEARCH_MILESTONE, then=Value(1)),
            When(category=CompanyLinkedInPost.Category.EVENT_ATTENDANCE, then=Value(2)),
            When(category=CompanyLinkedInPost.Category.HIRING, then=Value(3)),
            default=Value(4),
            output_field=IntegerField(),
        ))
        .order_by("ticker_priority", "-post_date")[:10]
    )

    querystring = request.GET.copy()
    querystring.pop("page", None)
    querystring_no_view = querystring.copy()
    querystring_no_view.pop("view", None)

    return render(
        request,
        "companymap/social_room.html",
        {
            "page": page,
            "page_range": page_range,
            "company_options": company_options,
            "state_options": state_options,
            "segment_options": segment_options,
            "category_options": category_options,
            "ticker_posts": ticker_posts,
            "q": q,
            "selected_companies": set(company_ids),
            "selected_states": set(state_codes),
            "selected_segments": set(segments),
            "selected_categories": set(categories),
            "view": view,
            "saved_count": saved_count,
            "querystring": querystring.urlencode(),
            "querystring_no_view": querystring_no_view.urlencode(),
            "total_posts": CompanyLinkedInPost.objects.count(),
        },
    )


@require_POST
def social_room_toggle_save(request, post_id):
    post = get_object_or_404(CompanyLinkedInPost, id=post_id)
    post.is_saved = not post.is_saved
    post.save(update_fields=["is_saved"])
    return JsonResponse({"saved": post.is_saved})

# Create your views here.
