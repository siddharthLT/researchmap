from django.db import models
from django.utils.text import slugify


class CompanyList(models.Model):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    companies = models.ManyToManyField(
        "companymap.Company",
        through="CompanyListItem",
        related_name="contactdb_lists",
        blank=True,
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class CompanyListItem(models.Model):
    list = models.ForeignKey(CompanyList, related_name="items", on_delete=models.CASCADE)
    company = models.ForeignKey(
        "companymap.Company",
        related_name="contactdb_list_items",
        on_delete=models.CASCADE,
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["company__name"]
        constraints = [
            models.UniqueConstraint(fields=["list", "company"], name="unique_company_per_list"),
        ]

    def __str__(self):
        return f"{self.company} in {self.list}"


class PersonList(models.Model):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    people = models.ManyToManyField(
        "Person",
        through="PersonListItem",
        related_name="lists",
        blank=True,
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Person(models.Model):
    class Segment(models.TextChoices):
        CDMO = "cdmo", "CDMO"
        CRO = "cro", "CRO"
        REAGENTS = "reagents", "Reagents & Lab Tools"
        EQUIPMENT = "equipment", "Equipment & Devices"
        PHARMA = "pharma", "Pharma / Biotech"
        CONSULTING = "consulting", "Consulting & BD"
        NON_PHARMA = "non_pharma", "Non-Pharma"

    name = models.CharField(max_length=255)
    title = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    linkedin_url = models.URLField(blank=True)
    company = models.ForeignKey(
        "companymap.Company",
        related_name="contactdb_people",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    company_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Free-text company name, used when there's no matching Company record.",
    )
    segment = models.CharField(max_length=16, choices=Segment.choices, blank=True)
    prior_connections = models.JSONField(
        default=list,
        blank=True,
        help_text="Names of the warm-connection network(s) this person belongs to.",
    )
    notes = models.TextField(blank=True)
    raw_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "people"

    def __str__(self):
        if self.title:
            return f"{self.name}, {self.title}"
        return self.name

    @property
    def display_company(self):
        return self.company.name if self.company else self.company_name


class CompanyBrief(models.Model):
    """Structured research brief for a company, normalized to a common set of
    sections regardless of which source report it came from (e.g. a Biolens
    PDF). One brief per Company; re-running an import updates it in place."""

    company = models.OneToOneField(
        "companymap.Company",
        related_name="brief",
        on_delete=models.CASCADE,
    )
    legal_name = models.CharField(max_length=255, blank=True)
    founded = models.CharField(max_length=64, blank=True)
    headquarters = models.CharField(max_length=255, blank=True)
    employee_count = models.CharField(max_length=64, blank=True)
    ownership = models.CharField(max_length=255, blank=True)
    global_presence = models.CharField(max_length=255, blank=True)

    nature = models.TextField(blank=True)
    service_model = models.TextField(blank=True)
    client_profile = models.TextField(blank=True)
    modality_focus = models.TextField(blank=True)
    therapeutic_focus = models.TextField(blank=True)
    trial_phase_preference = models.TextField(blank=True)

    decision_makers = models.JSONField(
        default=list,
        blank=True,
        help_text="List of {name, title, note} dicts.",
    )
    latest_signals_period = models.CharField(max_length=128, blank=True)
    latest_signals = models.JSONField(default=list, blank=True, help_text="List of bullet strings.")

    opportunity_assessment = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    sources = models.JSONField(default=list, blank=True, help_text="List of citation strings/URLs.")
    source_document = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "company brief"

    def __str__(self):
        return f"Brief: {self.company.name}"


class PersonListItem(models.Model):
    list = models.ForeignKey(PersonList, related_name="items", on_delete=models.CASCADE)
    person = models.ForeignKey(Person, related_name="list_items", on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["person__name"]
        constraints = [
            models.UniqueConstraint(fields=["list", "person"], name="unique_person_per_list"),
        ]

    def __str__(self):
        return f"{self.person} in {self.list}"
