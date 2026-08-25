import re
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from companymap.models import Company, DecisionMaker
from contactdb.models import CompanyListItem, Person

FIELDS_TO_BACKFILL = [
    "url", "domain", "linkedin_url", "logo_url", "address", "city", "state_code",
    "state_name", "country", "postal_code", "latitude", "longitude",
    "employee_count", "industry", "account_stage", "account_owner",
    "product_category", "sub_type", "segment", "modality", "priority",
    "account_list_source", "annual_revenue", "funding_data", "revenue_data", "notes",
]


def score(company):
    filled = sum(1 for f in FIELDS_TO_BACKFILL if getattr(company, f))
    has_coords = bool(company.latitude and company.longitude)
    clean_name = 0 if re.search(r"\(\d+\)|\(CCS\)", company.name) else 1
    not_shouty = 0 if company.name.isupper() else 1
    return (has_coords, filled, clean_name, not_shouty, -company.id)


class Command(BaseCommand):
    help = "Find companies sharing a domain (or a near-identical name at the same city) and merge them into one canonical record."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        companies = list(Company.objects.all())

        by_domain = defaultdict(list)
        for c in companies:
            if c.domain:
                by_domain[c.domain.lower()].append(c)
        groups = [g for g in by_domain.values() if len(g) > 1]

        # Known same-entity pair not sharing a domain (different TLD/rebrand).
        extra_pairs = [("Comprehensive Cell Solutions", "Comprehensive Cell Solutions (CCS)")]
        for name_a, name_b in extra_pairs:
            a = Company.objects.filter(name=name_a).first()
            b = Company.objects.filter(name=name_b).first()
            if a and b:
                groups.append([a, b])

        total_merged = 0
        for group in groups:
            canonical = max(group, key=score)
            duplicates = [c for c in group if c.id != canonical.id]
            self.stdout.write(f"KEEP  {canonical.id} {canonical.name!r} [{canonical.domain}]")
            for dup in duplicates:
                self.stdout.write(f"  MERGE {dup.id} {dup.name!r} [{dup.domain}] -> {canonical.id}")

            if dry_run:
                continue

            for field in FIELDS_TO_BACKFILL:
                if not getattr(canonical, field):
                    for dup in duplicates:
                        value = getattr(dup, field)
                        if value:
                            setattr(canonical, field, value)
                            break
            canonical.save()

            for dup in duplicates:
                Person.objects.filter(company=dup).update(company=canonical)

                for item in CompanyListItem.objects.filter(company=dup):
                    if CompanyListItem.objects.filter(list=item.list, company=canonical).exists():
                        item.delete()
                    else:
                        item.company = canonical
                        item.save(update_fields=["company"])

                for dm in DecisionMaker.objects.filter(company=dup):
                    if DecisionMaker.objects.filter(company=canonical, name=dm.name).exists():
                        dm.delete()
                    else:
                        dm.company = canonical
                        dm.save(update_fields=["company"])

                dup.delete()
                total_merged += 1

        self.stdout.write(self.style.SUCCESS(
            f"{'Would merge' if dry_run else 'Merged'} {total_merged} duplicate companies across {len(groups)} groups."
        ))
