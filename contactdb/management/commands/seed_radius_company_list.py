from math import atan2, cos, radians, sin, sqrt

from django.core.management.base import BaseCommand
from django.db import transaction

from companymap.models import Company
from contactdb.models import CompanyList, CompanyListItem

EARTH_RADIUS_MI = 3958.8


def haversine_mi(lat1, lon1, lat2, lon2):
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_MI * atan2(sqrt(a), sqrt(1 - a))


class Command(BaseCommand):
    help = "Create/update a ContactDB company list from every mapped company within a mile radius of a point."

    def add_arguments(self, parser):
        parser.add_argument("list_name", type=str)
        parser.add_argument("center_lat", type=float)
        parser.add_argument("center_lon", type=float)
        parser.add_argument("--min-miles", type=float, default=0)
        parser.add_argument("--max-miles", type=float, required=True)
        parser.add_argument("--description", type=str, default="")

    @transaction.atomic
    def handle(self, *args, **options):
        company_list, created = CompanyList.objects.get_or_create(
            name=options["list_name"],
            defaults={"description": options["description"]},
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created list '{company_list.name}'."))
        elif options["description"]:
            company_list.description = options["description"]
            company_list.save(update_fields=["description"])

        lat, lon = options["center_lat"], options["center_lon"]
        min_mi, max_mi = options["min_miles"], options["max_miles"]

        matched_ids = []
        for company in Company.objects.filter(latitude__isnull=False, longitude__isnull=False):
            distance = haversine_mi(lat, lon, float(company.latitude), float(company.longitude))
            if min_mi <= distance <= max_mi:
                matched_ids.append(company.id)

        existing_ids = set(company_list.items.values_list("company_id", flat=True))
        new_items = [
            CompanyListItem(list=company_list, company_id=company_id)
            for company_id in matched_ids
            if company_id not in existing_ids
        ]
        CompanyListItem.objects.bulk_create(new_items)

        stale_ids = existing_ids - set(matched_ids)
        removed = 0
        if stale_ids:
            removed, _ = company_list.items.filter(company_id__in=stale_ids).delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Matched {len(matched_ids)} companies within {min_mi}-{max_mi} miles. "
                f"Added {len(new_items)}, removed {removed} stale, list now has {company_list.items.count()}."
            )
        )
