import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

from django.core.management.base import BaseCommand, CommandError

from companymap.models import Company, DecisionMaker


CITY_CENTROIDS = {
    ("Alameda", "CA"): (37.779927, -122.282185),
    ("Bakersfield", "CA"): (35.373292, -119.018713),
    ("Bellevue", "WA"): (47.610149, -122.201516),
    ("Bend", "OR"): (44.058173, -121.315310),
    ("Bothell", "WA"): (47.760111, -122.205445),
    ("Brisbane", "CA"): (37.680766, -122.399972),
    ("San Francisco", "CA"): (37.774929, -122.419416),
    ("South San Francisco", "CA"): (37.654656, -122.407750),
    ("San Diego", "CA"): (32.715736, -117.161087),
    ("Los Angeles", "CA"): (34.052235, -118.243683),
    ("Camarillo", "CA"): (34.216393, -119.037602),
    ("Carlsbad", "CA"): (33.158093, -117.350594),
    ("Commerce", "CA"): (34.000569, -118.159792),
    ("Costa Mesa", "CA"): (33.641132, -117.918669),
    ("El Cajon", "CA"): (32.794773, -116.962527),
    ("Emeryville", "CA"): (37.839502, -122.289227),
    ("Folsom", "CA"): (38.677959, -121.176058),
    ("Foster City", "CA"): (37.558546, -122.271079),
    ("Fremont", "CA"): (37.548540, -121.988583),
    ("Hayward", "CA"): (37.668821, -122.080796),
    ("Hercules", "CA"): (38.017145, -122.288581),
    ("Irvine", "CA"): (33.684567, -117.826505),
    ("Laguna Hills", "CA"): (33.599723, -117.699389),
    ("Lake Forest", "CA"): (33.646966, -117.689218),
    ("Livermore", "CA"): (37.681874, -121.768009),
    ("March Air Reserve Base", "CA"): (33.892090, -117.263560),
    ("Menlo Park", "CA"): (37.452960, -122.181725),
    ("Milpitas", "CA"): (37.432334, -121.899574),
    ("Newark", "CA"): (37.529659, -122.040240),
    ("Oceanside", "CA"): (33.195870, -117.379483),
    ("Palo Alto", "CA"): (37.441883, -122.143019),
    ("Pleasanton", "CA"): (37.662431, -121.874679),
    ("Rancho Cordova", "CA"): (38.589072, -121.302728),
    ("Redwood City", "CA"): (37.485215, -122.236355),
    ("San Carlos", "CA"): (37.507159, -122.260522),
    ("San Clemente", "CA"): (33.426972, -117.611992),
    ("San Jose", "CA"): (37.338208, -121.886329),
    ("San Rafael", "CA"): (37.973535, -122.531087),
    ("Santa Clara", "CA"): (37.354108, -121.955236),
    ("Thousand Oaks", "CA"): (34.170561, -118.837594),
    ("Vista", "CA"): (33.200037, -117.242536),
    ("Seattle", "WA"): (47.606209, -122.332071),
    ("Spokane", "WA"): (47.658780, -117.426047),
    ("Portland", "OR"): (45.515232, -122.678385),
    ("Newberg", "OR"): (45.300118, -122.973156),
    ("Boston", "MA"): (42.360083, -71.058880),
    ("Cambridge", "MA"): (42.373616, -71.109733),
    ("Marlborough", "MA"): (42.345927, -71.552287),
    ("New York", "NY"): (40.712776, -74.005974),
    ("Philadelphia", "PA"): (39.952584, -75.165222),
    ("Princeton", "NJ"): (40.357298, -74.667223),
    ("Newark", "NJ"): (40.735657, -74.172367),
    ("Upper Saddle River", "NJ"): (41.058431, -74.098475),
    ("Washington", "DC"): (38.907192, -77.036871),
    ("Baltimore", "MD"): (39.290385, -76.612189),
    ("Germantown", "MD"): (39.173162, -77.271650),
    ("Raleigh", "NC"): (35.779590, -78.638179),
    ("Durham", "NC"): (35.994033, -78.898619),
    ("Atlanta", "GA"): (33.749000, -84.387978),
    ("Miami", "FL"): (25.761681, -80.191788),
    ("Tampa", "FL"): (27.950575, -82.457178),
    ("Oakdale", "MN"): (44.963021, -92.964936),
}

WEST_COAST_STATES = {"CA", "OR", "WA"}
EAST_COAST_STATES = {
    "ME",
    "NH",
    "MA",
    "RI",
    "CT",
    "NY",
    "NJ",
    "DE",
    "MD",
    "DC",
    "VA",
    "NC",
    "SC",
    "GA",
    "FL",
    "PA",
}
STATE_NAME_TO_CODE = {
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "District of Columbia": "DC",
    "Florida": "FL",
    "Georgia": "GA",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
}


class Command(BaseCommand):
    help = "Import company map data from a CSV file."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str)
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing companies and decision makers before importing.",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"])
        if not csv_path.exists():
            raise CommandError(f"CSV file not found: {csv_path}")

        if options["clear"]:
            Company.objects.all().delete()

        created = 0
        updated = 0
        with csv_path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            self._validate_headers(reader.fieldnames or [])
            for row_number, row in enumerate(reader, start=2):
                company, was_created = self._upsert_company(row, row_number)
                self._sync_decision_makers(company, row)
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(
            self.style.SUCCESS(f"Imported {created} new companies and updated {updated}.")
        )

    def _validate_headers(self, headers):
        required = {"name"} if "name" in headers else {"Company Name"}
        missing = required - {header.strip() for header in headers}
        if missing:
            raise CommandError(f"Missing required CSV columns: {', '.join(sorted(missing))}")

    def _upsert_company(self, row, row_number):
        name = self._value(row, "name", "Company Name")
        city = self._value(row, "city", "Company City")
        state_name = self._value(row, "state_name", "Company State")
        state_code = self._state_code(self._value(row, "state_code"), state_name)
        country = self._value(row, "country", "Company Country")
        if not name:
            raise CommandError(f"Row {row_number}: name is required.")

        latitude, longitude = self._coordinates(row, city, state_code, row_number)
        url = self._value(row, "url", "Website")
        defaults = {
            "url": url,
            "domain": self._value(row, "domain") or self._domain_from_url(url),
            "linkedin_url": self._value(row, "linkedin_url", "Company Linkedin Url"),
            "logo_url": self._value(row, "logo_url", "Logo Url"),
            "address": self._value(row, "address", "Company Address"),
            "state_name": state_name,
            "country": country,
            "postal_code": self._value(row, "postal_code", "Company Postal Code"),
            "region": self._region_for_state(state_code),
            "latitude": latitude,
            "longitude": longitude,
            "employee_count": self._integer(row, "# Employees"),
            "industry": self._value(row, "industry", "Industry"),
            "account_stage": self._value(row, "Account Stage"),
            "account_owner": self._value(row, "Account Owner"),
            "product_category": self._value(row, "Product Category"),
            "sub_type": self._value(row, "Sub-type"),
            "segment": self._value(row, "Segment", "Customer segment"),
            "priority": self._value(row, "Priority"),
            "account_list_source": self._value(row, "Account List Source"),
            "annual_revenue": self._integer(row, "annual_revenue", "Annual Revenue"),
            "funding_data": self._funding_data(row),
            "revenue_data": self._revenue_data(row),
            "notes": self._notes(row),
            "raw_data": self._raw_data(row),
        }
        return Company.objects.update_or_create(
            name=name,
            city=city,
            state_code=state_code,
            defaults=defaults,
        )

    def _sync_decision_makers(self, company, row):
        raw = self._value(row, "decision_makers")
        if not raw:
            return

        company.decision_makers.all().delete()
        for item in raw.split(";"):
            parts = [part.strip() for part in item.split("|")]
            if not parts or not parts[0]:
                continue
            DecisionMaker.objects.create(
                company=company,
                name=parts[0],
                title=parts[1] if len(parts) > 1 else "",
                email=parts[2] if len(parts) > 2 else "",
                linkedin_url=parts[3] if len(parts) > 3 else "",
            )

    def _coordinates(self, row, city, state_code, row_number):
        latitude = self._value(row, "latitude")
        longitude = self._value(row, "longitude")
        if latitude and longitude:
            try:
                return Decimal(latitude), Decimal(longitude)
            except InvalidOperation as exc:
                raise CommandError(f"Row {row_number}: invalid latitude or longitude.") from exc

        centroid = CITY_CENTROIDS.get((city, state_code))
        if centroid:
            return Decimal(str(centroid[0])), Decimal(str(centroid[1]))

        return None, None

    def _region_for_state(self, state_code):
        if state_code in WEST_COAST_STATES:
            return Company.Region.WEST_COAST
        if state_code in EAST_COAST_STATES:
            return Company.Region.EAST_COAST
        return Company.Region.OTHER

    def _state_code(self, state_code, state_name):
        if state_code:
            return state_code.upper()
        return STATE_NAME_TO_CODE.get(state_name, "")

    def _domain_from_url(self, url):
        if not url:
            return ""
        parsed = urlparse(url if "://" in url else f"https://{url}")
        return parsed.netloc.removeprefix("www.").lower()

    def _funding_data(self, row):
        direct = self._value(row, "funding_data")
        if direct:
            return direct
        parts = []
        total = self._value(row, "Total Funding")
        latest = self._value(row, "Latest Funding")
        latest_amount = self._value(row, "Latest Funding Amount")
        raised_at = self._value(row, "Last Raised At")
        if total:
            parts.append(f"Total funding: {total}")
        if latest:
            latest_text = f"Latest funding: {latest}"
            if latest_amount:
                latest_text += f" ({latest_amount})"
            if raised_at:
                latest_text += f" on {raised_at}"
            parts.append(latest_text)
        return "; ".join(parts)

    def _revenue_data(self, row):
        direct = self._value(row, "revenue_data")
        if direct:
            return direct
        revenue = self._value(row, "Annual Revenue")
        return f"Annual revenue: {revenue}" if revenue else ""

    def _notes(self, row):
        direct = self._value(row, "notes")
        if direct:
            return direct
        notes = []
        for label, key in (
            ("Description", "Short Description"),
            ("Keywords", "Keywords"),
            ("Technologies", "Technologies"),
            ("Prior connection", "Prior connection"),
            ("Warm path", "Warm Path"),
            ("Signal", "Signal"),
        ):
            value = self._value(row, key)
            if value:
                notes.append(f"{label}: {value}")
        return "\n\n".join(notes)

    def _raw_data(self, row):
        return {
            key.strip(): (value or "").strip()
            for key, value in row.items()
            if key and (value or "").strip()
        }

    def _integer(self, row, *keys):
        raw = self._value(row, *keys).replace(",", "")
        if not raw:
            return None
        try:
            return int(float(raw))
        except ValueError:
            return None

    def _value(self, row, *keys):
        for key in keys:
            value = (row.get(key) or "").strip()
            if value:
                return value
        return ""
