from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from companymap.models import Company
from contactdb.models import Person
from contactdb.stakeholder import classify_title


class Command(BaseCommand):
    help = (
        "Classify each Person's stakeholder_role (decision maker / champion / "
        "influencer / end user) from their job title, for people at the given "
        "companies. Rule-based -- see contactdb/stakeholder.py."
    )

    def add_arguments(self, parser):
        parser.add_argument("company_names", nargs="+", type=str)

    @transaction.atomic
    def handle(self, *args, **options):
        counts = {}
        total = 0
        for name in options["company_names"]:
            try:
                company = Company.objects.get(name=name)
            except Company.DoesNotExist:
                raise CommandError(f"Company not found: {name!r}")

            people = list(Person.objects.filter(company=company))
            for person in people:
                role = classify_title(person.title)
                person.stakeholder_role = role
                person.save(update_fields=["stakeholder_role"])
                counts[role or "unclassified"] = counts.get(role or "unclassified", 0) + 1
                total += 1

            self.stdout.write(f"{name}: classified {len(people)} people")

        self.stdout.write(self.style.SUCCESS(f"Total: {total} people -- {counts}"))
