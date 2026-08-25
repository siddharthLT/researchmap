import csv
import html
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from contactdb.models import Person

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif")

SEGMENT_LABEL_TO_VALUE = {
    "CDMO": Person.Segment.CDMO,
    "CRO": Person.Segment.CRO,
    "Reagents & Lab Tools": Person.Segment.REAGENTS,
    "Equipment & Devices": Person.Segment.EQUIPMENT,
    "Pharma / Biotech": Person.Segment.PHARMA,
    "Consulting & BD": Person.Segment.CONSULTING,
    "Non-Pharma": Person.Segment.NON_PHARMA,
}

CONNECTOR_PAGES = {
    "vedant": "Vedant",
    "pk": "PK",
    "naren": "Naren",
    "mukesh": "Mukesh",
    "lavanya": "Lavanya",
}


def canonicalize(name):
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def strip_tags(text):
    return re.sub(r"<[^<]+?>", "", text).strip()


class Command(BaseCommand):
    help = (
        "Backfill Person.segment and Person.prior_connections from the generated "
        "connections report HTML files and the source warm-connections CSV."
    )

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str)
        parser.add_argument("connections_dir", type=str)

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"])
        connections_dir = Path(options["connections_dir"])
        if not csv_path.exists():
            raise CommandError(f"CSV file not found: {csv_path}")
        if not connections_dir.exists():
            raise CommandError(f"Connections dir not found: {connections_dir}")

        company_segment = self._extract_company_segments(connections_dir)
        self.stdout.write(f"Extracted segment classification for {len(company_segment)} companies.")

        with csv_path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))

        updated = 0
        unmatched_person = 0
        unmatched_segment = 0

        for row in rows:
            first = (row.get("First Name") or "").strip()
            last = (row.get("Last Name") or "").strip()
            name = f"{first} {last}".strip()
            if not name:
                continue
            company_name = self._company_name(row)
            connectors = [c.strip() for c in (row.get("Prior Connection") or "").split(",") if c.strip()]

            person = self._match_person(name, company_name, row.get("Email", "").strip())
            if person is None:
                unmatched_person += 1
                continue

            changed = False
            if company_name:
                segment = company_segment.get(canonicalize(company_name), "")
                if segment and person.segment != segment:
                    person.segment = segment
                    changed = True
                elif not segment:
                    unmatched_segment += 1

            merged = sorted(set(person.prior_connections) | set(connectors))
            if merged != person.prior_connections:
                person.prior_connections = merged
                changed = True

            if changed:
                person.save(update_fields=["segment", "prior_connections"])
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated {updated} people. Unmatched person rows: {unmatched_person}. "
                f"Rows with no segment match: {unmatched_segment}."
            )
        )

    def _extract_company_segments(self, connections_dir):
        company_segment = {}
        for slug in CONNECTOR_PAGES:
            path = connections_dir / f"{slug}.html"
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8")
            sections = re.split(r'<section class="cat-section"', content)[1:]
            for sec in sections:
                title_match = re.search(r"<h2>([^<]+)<span", sec)
                if not title_match:
                    continue
                label = html.unescape(strip_tags(title_match.group(1)))
                segment_value = SEGMENT_LABEL_TO_VALUE.get(label)
                if not segment_value:
                    continue
                rows = re.findall(
                    r"<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>", sec, re.S
                )
                for _name, _title, company in rows:
                    clean = html.unescape(strip_tags(company))
                    if clean:
                        company_segment[canonicalize(clean)] = segment_value
        return company_segment

    def _company_name(self, row):
        raw = (row.get("Company Name") or "").strip()
        if raw.lower().endswith(IMAGE_EXTENSIONS):
            return (row.get("Company Name for Emails") or "").strip()
        return raw

    def _match_person(self, name, company_name, email):
        if email:
            person = Person.objects.filter(name=name, email=email).first()
            if person:
                return person
        candidates = Person.objects.filter(name=name)
        count = candidates.count()
        if count == 1:
            return candidates.first()
        if count > 1 and company_name:
            match = candidates.filter(company_name=company_name).first()
            if match:
                return match
            match = candidates.filter(company__name__iexact=company_name).first()
            if match:
                return match
        return candidates.first()
