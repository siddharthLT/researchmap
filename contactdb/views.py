from django.db.models import Count
from django.shortcuts import get_object_or_404, render

from .models import CompanyList, PersonList


def home(request):
    company_lists = CompanyList.objects.annotate(item_count=Count("items"))
    person_lists = PersonList.objects.annotate(item_count=Count("items"))
    return render(
        request,
        "contactdb/home.html",
        {"company_lists": company_lists, "person_lists": person_lists},
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
