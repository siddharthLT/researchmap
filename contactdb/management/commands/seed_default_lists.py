from django.core.management.base import BaseCommand
from django.db import transaction

from companymap.models import Company
from contactdb.models import CompanyList, CompanyListItem

ALL_US_COMPANIES_LIST = "All US Companies"


class Command(BaseCommand):
    help = (
        "Seed default ContactDB lists. Creates the 'All US Companies' company list "
        "and adds every Company from the map database to it."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        company_list, created = CompanyList.objects.get_or_create(
            name=ALL_US_COMPANIES_LIST,
            defaults={"description": "Every company currently in the company map database."},
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created list '{company_list.name}'."))

        existing_ids = set(company_list.items.values_list("company_id", flat=True))
        new_items = [
            CompanyListItem(list=company_list, company_id=company_id)
            for company_id in Company.objects.exclude(id__in=existing_ids).values_list("id", flat=True)
        ]
        CompanyListItem.objects.bulk_create(new_items)

        total = company_list.items.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Added {len(new_items)} new companies to '{company_list.name}' ({total} total)."
            )
        )
