from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import Company


class CompanyMapTests(TestCase):
    def test_import_command_creates_company_and_decision_makers(self):
        call_command("import_companies", "companymap/sample_companies.csv")

        company = Company.objects.get(name="Example Biotech")

        self.assertEqual(company.city, "San Francisco")
        self.assertEqual(company.state_code, "CA")
        self.assertEqual(company.region, Company.Region.WEST_COAST)
        self.assertEqual(company.decision_makers.count(), 2)

    def test_company_map_data_returns_states_cities_and_companies(self):
        call_command("import_companies", "companymap/sample_companies.csv")

        response = self.client.get(reverse("companymap:company_map_data"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["states"]), 2)
        self.assertEqual(len(payload["cities"]), 2)
        self.assertEqual(len(payload["companies"]), 2)
        self.assertEqual(payload["companies"][0]["decision_makers"][0]["name"], "Jane Doe")

# Create your tests here.
