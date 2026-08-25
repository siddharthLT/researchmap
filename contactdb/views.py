import json
import re
from collections import Counter

from django.db.models import Count
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render

from companymap.models import Company

from .models import CompanyBrief, CompanyList, Person, PersonList

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

# Supply-side vendors first, pharma/biotech sponsors next, consulting after
# that, non-pharma last, unclassified at the very end.
SEGMENT_ORDER = [
    Person.Segment.CDMO,
    Person.Segment.CRO,
    Person.Segment.REAGENTS,
    Person.Segment.EQUIPMENT,
    Person.Segment.PHARMA,
    Person.Segment.CONSULTING,
    Person.Segment.NON_PHARMA,
]

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
    warm_company_ids = set(
        Person.objects.exclude(prior_connections=[])
        .filter(company_id__in=[c.id for c in companies])
        .values_list("company_id", flat=True)
        .distinct()
    )
    modality_counts = Counter()
    segment_counts = Counter()
    for company in companies:
        company.has_warm_connection = company.id in warm_company_ids
        company.modality_tags = [t.strip() for t in company.modality.split(",") if t.strip()]
        company.data_modality = "|".join(company.modality_tags)
        company.data_segment = company.segment
        company.data_warm = "yes" if company.has_warm_connection else "no"
        modality_counts.update(company.modality_tags)
        if company.segment:
            segment_counts[company.segment] += 1
        company.export_json = json.dumps(
            {
                "Name": company.name,
                "Website": company.url,
                "Modality": company.modality,
                "Segment": company.segment,
                "Location": ", ".join(part for part in (company.city, company.state_code) if part),
                "Industry": company.industry,
                "Product Category": company.product_category,
                "Employees": company.employee_count,
                "Annual Revenue": company.annual_revenue,
                "Decision Makers": company.decision_maker_names,
                "Warm Connection": "Yes" if company.has_warm_connection else "",
            }
        )
    modality_options = sorted(modality_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    segment_options = sorted(segment_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return render(
        request,
        "contactdb/company_list_detail.html",
        {
            "company_list": company_list,
            "companies": companies,
            "modality_options": modality_options,
            "segment_options": segment_options,
            "warm_count": len(warm_company_ids),
        },
    )


def person_list_detail(request, slug):
    person_list = get_object_or_404(PersonList, slug=slug)
    people = person_list.people.all().select_related("company").order_by("name")
    segment_labels = dict(Person.Segment.choices)
    modality_counts = Counter()
    segment_counts = Counter()
    for person in people:
        modality = person.company.modality if person.company else ""
        person.modality_tags = [t.strip() for t in modality.split(",") if t.strip()]
        person.data_modality = "|".join(person.modality_tags)
        person.segment_label = segment_labels.get(person.segment, "")
        person.data_segment = person.segment_label
        person.has_warm_connection = bool(person.prior_connections)
        person.data_warm = "yes" if person.has_warm_connection else "no"
        modality_counts.update(person.modality_tags)
        if person.segment_label:
            segment_counts[person.segment_label] += 1
        person.export_json = json.dumps(
            {
                "Name": person.name,
                "Title": person.title,
                "Company": person.display_company,
                "Modality": modality,
                "Segment": person.segment_label,
                "Warm Connection": "Yes" if person.has_warm_connection else "",
                "Phone": person.phone,
                "Email": person.email,
                "LinkedIn": person.linkedin_url,
                "Notes": person.notes,
            }
        )
    modality_options = sorted(modality_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    segment_options = sorted(segment_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return render(
        request,
        "contactdb/person_list_detail.html",
        {
            "person_list": person_list,
            "people": people,
            "modality_options": modality_options,
            "segment_options": segment_options,
        },
    )


def connection_universe(request, slug):
    connector = CONNECTOR_SLUGS.get(slug)
    if not connector:
        raise Http404("Unknown connections page.")

    people = Person.objects.filter(prior_connections__contains=[connector]).select_related("company").order_by("name")
    total = people.count()
    segment_labels = dict(Person.Segment.choices)

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
                "export_json": json.dumps(
                    {
                        "Name": person.name,
                        "Title": person.title,
                        "Company": person.display_company,
                        "Location": location,
                        "Segment": segment_labels.get(person.segment, "Unclassified"),
                        "High Fit": "Yes" if _is_high_fit(person.segment, person.title) else "",
                    }
                ),
            }
        )

    segment_groups = {}
    for row in rows:
        segment_groups.setdefault(row["segment"], []).append(row)

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
    order_index = {value: i for i, value in enumerate(SEGMENT_ORDER)}
    segments.sort(key=lambda s: order_index.get(s["value"], len(SEGMENT_ORDER)))
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


def company_brief(request, company_id):
    company = get_object_or_404(Company, pk=company_id)
    company_lists = CompanyList.objects.filter(items__company=company).order_by("name")
    people = Person.objects.filter(company=company).prefetch_related("lists").order_by("name")
    company.has_warm_connection = any(person.prior_connections for person in people)

    sections = {}
    unlisted = []
    for person in people:
        lists = list(person.lists.all())
        if not lists:
            unlisted.append(person)
            continue
        for person_list in lists:
            sections.setdefault(person_list, []).append(person)

    section_list = [
        {"list": person_list, "people": people_in_list}
        for person_list, people_in_list in sorted(sections.items(), key=lambda kv: kv[0].name)
    ]
    if unlisted:
        section_list.append({"list": None, "people": unlisted})

    brief = CompanyBrief.objects.filter(company=company).first()

    return render(
        request,
        "contactdb/company_brief.html",
        {
            "company": company,
            "company_lists": company_lists,
            "sections": section_list,
            "total_people": people.count(),
            "brief": brief,
        },
    )
