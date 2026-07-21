import csv
import io
from decimal import Decimal

import requests
from django.core.management.base import BaseCommand, CommandError

from companymap.management.commands.import_companies import CITY_CENTROIDS
from companymap.models import Company

CENSUS_BATCH_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
BATCH_SIZE = 500


class Command(BaseCommand):
    help = (
        "Geocode US companies that have a full street address, using the free US Census "
        "batch geocoder, so they plot at their real location instead of a shared city centroid."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Re-geocode every eligible company, even ones that already have precise coordinates.",
        )

    def handle(self, *args, **options):
        candidates = list(
            Company.objects.filter(
                address__regex=r"^\s*\d",
                country__icontains="United States",
            ).exclude(postal_code="")
        )

        if not options["all"]:
            candidates = [c for c in candidates if self._needs_geocoding(c)]

        if not candidates:
            self.stdout.write("No companies need geocoding.")
            return

        self.stdout.write(
            f"Geocoding {len(candidates)} companies via the US Census batch geocoder..."
        )

        matched = 0
        for start in range(0, len(candidates), BATCH_SIZE):
            chunk = candidates[start:start + BATCH_SIZE]
            matched += self._geocode_chunk(chunk)

        self.stdout.write(
            self.style.SUCCESS(f"Matched {matched} of {len(candidates)} addresses.")
        )

    def _needs_geocoding(self, company):
        if company.latitude is None or company.longitude is None:
            return True
        centroid = CITY_CENTROIDS.get((company.city, company.state_code))
        if not centroid:
            return True
        return (
            abs(float(company.latitude) - centroid[0]) < 1e-6
            and abs(float(company.longitude) - centroid[1]) < 1e-6
        )

    def _geocode_chunk(self, companies):
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        for company in companies:
            street = company.address.split(",")[0].strip()
            zip_code = company.postal_code.split("-")[0].strip()
            writer.writerow([company.id, street, company.city, company.state_code, zip_code])

        try:
            response = requests.post(
                CENSUS_BATCH_URL,
                data={"benchmark": "Public_AR_Current"},
                files={"addressFile": ("addresses.csv", buffer.getvalue(), "text/csv")},
                timeout=120,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise CommandError(f"Census geocoder request failed: {exc}") from exc

        by_id = {company.id: company for company in companies}
        matched = 0
        for row in csv.reader(io.StringIO(response.text)):
            if len(row) < 3:
                continue
            company = by_id.get(int(row[0]))
            if not company or row[2] != "Match":
                continue
            lon_str, lat_str = row[5].split(",")
            company.latitude = Decimal(lat_str)
            company.longitude = Decimal(lon_str)
            company.save(update_fields=["latitude", "longitude"])
            matched += 1
        return matched
