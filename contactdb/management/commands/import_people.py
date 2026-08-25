import csv
from pathlib import Path
from urllib.parse import urlparse

from django.core.management.base import BaseCommand, CommandError

from companymap.models import Company
from contactdb.models import Person, PersonList, PersonListItem

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif")

# Apollo sometimes leaves a generic platform URL in the "Website" column
# instead of the contact's actual employer site (e.g. when it couldn't find
# one). Matching on these would silently attach the person to whichever
# Company record happens to carry the same bad domain.
GENERIC_DOMAINS = {
    "linkedin.com", "facebook.com", "twitter.com", "x.com", "instagram.com",
    "youtube.com", "google.com", "apollo.io", "crunchbase.com", "bit.ly",
}

PHONE_FIELDS = (
    "Work Direct Phone",
    "Mobile Phone",
    "Corporate Phone",
    "Home Phone",
    "Other Phone",
)

NOTE_FIELDS = (
    ("Prior connection", "Prior Connection"),
    ("Stage", "Stage"),
    ("Seniority", "Seniority"),
    ("Department", "Departments"),
    ("Keywords", "Keywords"),
)


class Command(BaseCommand):
    help = "Import a people/contacts CSV (Apollo-style export) into a ContactDB people list."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str)
        parser.add_argument(
            "--list",
            dest="list_name",
            required=True,
            help="Name of the PersonList to add every imported contact to (created if missing).",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"])
        if not csv_path.exists():
            raise CommandError(f"CSV file not found: {csv_path}")

        person_list, created = PersonList.objects.get_or_create(name=options["list_name"])
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created list '{person_list.name}'."))

        domain_to_company = {}
        name_to_company = {}
        for company in Company.objects.exclude(domain="").only("id", "name", "domain"):
            domain = company.domain.lower()
            if domain not in GENERIC_DOMAINS:
                domain_to_company[domain] = company
        for company in Company.objects.only("id", "name"):
            name_to_company.setdefault(company.name.strip().lower(), company)

        created_count = 0
        updated_count = 0
        added_to_list = 0

        with csv_path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            self._validate_headers(reader.fieldnames or [])
            for row_number, row in enumerate(reader, start=2):
                person, was_created, in_list = self._upsert_person(
                    row, row_number, person_list, domain_to_company, name_to_company
                )
                if was_created:
                    created_count += 1
                else:
                    updated_count += 1
                if in_list:
                    added_to_list += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {created_count} new people and updated {updated_count}. "
                f"{added_to_list} added to '{person_list.name}' (now {person_list.items.count()} total)."
            )
        )

    def _validate_headers(self, headers):
        required = {"First Name", "Last Name"}
        missing = required - {header.strip() for header in headers}
        if missing:
            raise CommandError(f"Missing required CSV columns: {', '.join(sorted(missing))}")

    def _upsert_person(self, row, row_number, person_list, domain_to_company, name_to_company):
        first_name = (row.get("First Name") or "").strip()
        last_name = (row.get("Last Name") or "").strip()
        name = f"{first_name} {last_name}".strip()
        if not name:
            raise CommandError(f"Row {row_number}: a first or last name is required.")

        email = (row.get("Email") or "").strip()
        company = self._match_company(row, domain_to_company, name_to_company)
        company_name = self._company_name(row)

        defaults = {
            "title": (row.get("Title") or "").strip(),
            "email": email,
            "phone": self._phone(row),
            "linkedin_url": (row.get("Person Linkedin Url") or "").strip(),
            "company": company,
            "company_name": "" if company else company_name,
            "notes": self._notes(row),
            "raw_data": {k: v for k, v in row.items() if k and (v or "").strip()},
        }

        if email:
            lookup = {"name": name, "email": email}
        elif company:
            lookup = {"name": name, "company": company}
        else:
            lookup = {"name": name, "company_name": company_name}
        person, was_created = Person.objects.update_or_create(defaults=defaults, **lookup)

        _, in_list = PersonListItem.objects.get_or_create(list=person_list, person=person)
        return person, was_created, in_list

    def _match_company(self, row, domain_to_company, name_to_company):
        website = (row.get("Website") or "").strip()
        if website:
            domain = urlparse(website if "://" in website else f"https://{website}").netloc
            domain = domain.removeprefix("www.").lower()
            if domain in GENERIC_DOMAINS:
                domain = None
            if domain and domain in domain_to_company:
                return domain_to_company[domain]

        company_name = self._company_name(row)
        if company_name:
            return name_to_company.get(company_name.lower())
        return None

    def _company_name(self, row):
        raw = (row.get("Company Name") or "").strip()
        if raw.lower().endswith(IMAGE_EXTENSIONS):
            # Apollo export artifact: a broken logo-image formula leaked its
            # filename into the company name column instead of the real name.
            return (row.get("Company Name for Emails") or "").strip()
        return raw

    def _phone(self, row):
        for field in PHONE_FIELDS:
            value = (row.get(field) or "").strip()
            if value:
                return value
        return ""

    def _notes(self, row):
        parts = []
        for label, key in NOTE_FIELDS:
            value = (row.get(key) or "").strip()
            if value:
                parts.append(f"{label}: {value}")
        return "\n".join(parts)
