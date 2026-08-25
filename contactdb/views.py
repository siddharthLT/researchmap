import re

from django.db.models import Count
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render

from .models import CompanyList, Person, PersonList

CONNECTOR_SLUGS = {
    "vedant": "Vedant",
    "pk": "PK",
    "naren": "Naren",
    "mukesh": "Mukesh",
    "lavanya": "Lavanya",
}

SEGMENT_COLOR = {
    Person.Segment.CDMO: "--s1",
    Person.Segment.CRO: "--s2",
    Person.Segment.REAGENTS: "--s3",
    Person.Segment.EQUIPMENT: "--s4",
    Person.Segment.PHARMA: "--s5",
    Person.Segment.CONSULTING: "--s6",
    Person.Segment.NON_PHARMA: "--s7",
}

# "High fit" = works at a supply-side vendor (CDMO/CRO/reagents/equipment) AND
# holds a role that's likely to influence or approve a vendor relationship
# (BD, C-suite, marketing, data/tech, transformation, or presales).
HIGH_FIT_SEGMENTS = {
    Person.Segment.CDMO,
    Person.Segment.CRO,
    Person.Segment.REAGENTS,
    Person.Segment.EQUIPMENT,
}
HIGH_FIT_ROLE_PATTERN = re.compile(
    r"\b("
    r"business\s+development|bd|partnerships?|alliance(?:s|\s+management)?"
    r"|chief\s+\w+(\s+\w+)?\s+officer|ce+o|cfo|coo|cto|cio|cmo|cso|chro|cbo"
    r"|marketing"
    r"|data|informatics|analytics|\bai\b|technology|\btech\b|software|digital"
    r"|transformation"
    r"|pre[- ]?sales|solutions?\s+engineer|sales\s+engineer"
    r")\b",
    re.IGNORECASE,
)


def _is_high_fit(segment, title):
    return segment in HIGH_FIT_SEGMENTS and bool(HIGH_FIT_ROLE_PATTERN.search(title or ""))


def home(request):
    company_lists = CompanyList.objects.annotate(item_count=Count("items"))
    person_lists = PersonList.objects.annotate(item_count=Count("items"))
    connections = [
        {"slug": slug, "name": name, "count": Person.objects.filter(prior_connections__contains=[name]).count()}
        for slug, name in CONNECTOR_SLUGS.items()
    ]
    return render(
        request,
        "contactdb/home.html",
        {"company_lists": company_lists, "person_lists": person_lists, "connections": connections},
    )


def company_list_detail(request, slug):
    company_list = get_object_or_404(CompanyList, slug=slug)
    companies = (
        company_list.companies.all()
        .prefetch_related("decision_makers")
        .order_by("name")
    )
    return render(
        request,
        "contactdb/company_list_detail.html",
        {"company_list": company_list, "companies": companies},
    )


def person_list_detail(request, slug):
    person_list = get_object_or_404(PersonList, slug=slug)
    people = person_list.people.all().select_related("company").order_by("name")
    return render(
        request,
        "contactdb/person_list_detail.html",
        {"person_list": person_list, "people": people},
    )


def connection_universe(request, slug):
    connector = CONNECTOR_SLUGS.get(slug)
    if not connector:
        raise Http404("Unknown connections page.")

    people = Person.objects.filter(prior_connections__contains=[connector]).select_related("company").order_by("name")
    total = people.count()

    rows = []
    for person in people:
        raw = person.raw_data or {}
        city = raw.get("City") or (person.company.city if person.company else "")
        state = raw.get("State") or (person.company.state_name if person.company else "")
        location = ", ".join(part for part in (city, state) if part)
        rows.append(
            {
                "id": person.id,
                "name": person.name,
                "title": person.title,
                "company": person.display_company,
                "location": location,
                "segment": person.segment,
                "has_email": bool(person.email),
                "has_linkedin": bool(person.linkedin_url),
                "high_fit": _is_high_fit(person.segment, person.title),
            }
        )

    segment_groups = {}
    for row in rows:
        segment_groups.setdefault(row["segment"], []).append(row)

    segment_labels = dict(Person.Segment.choices)
    segments = []
    for value, group in segment_groups.items():
        label = segment_labels.get(value, "Unclassified")
        color = SEGMENT_COLOR.get(value, "--muted")
        count = len(group)
        segments.append(
            {
                "value": value or "unclassified",
                "label": label,
                "color": color,
                "count": count,
                "pct": round(100 * count / total) if total else 0,
                "people": sorted(group, key=lambda r: r["name"]),
            }
        )
    segments.sort(key=lambda s: -s["count"])
    high_fit_total = sum(1 for row in rows if row["high_fit"])

    return render(
        request,
        "contactdb/connections/report.html",
        {
            "connector": connector,
            "slug": slug,
            "total": total,
            "segments": segments,
            "high_fit_total": high_fit_total,
        },
    )


def person_contact(request, person_id):
    person = get_object_or_404(Person, pk=person_id)
    return JsonResponse({"email": person.email, "linkedin_url": person.linkedin_url})
