from django.db import models


class Company(models.Model):
    class Region(models.TextChoices):
        WEST_COAST = "west", "West Coast"
        EAST_COAST = "east", "East Coast"
        OTHER = "other", "Other"

    class SynthegoRelation(models.TextChoices):
        COMPETITOR = "competitor", "Synthego Competitor"
        ADJACENT = "adjacent", "Synthego Adjacent"
        PARTNER = "partner", "Synthego Partner"
        NO_RELATION = "no_relation", "No Relation with Synthego"

    name = models.CharField(max_length=255)
    url = models.URLField(blank=True)
    domain = models.CharField(max_length=255, blank=True)
    linkedin_url = models.URLField(blank=True)
    logo_url = models.URLField(blank=True)
    address = models.CharField(max_length=500, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state_code = models.CharField(max_length=2, blank=True)
    state_name = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=32, blank=True)
    region = models.CharField(max_length=12, choices=Region.choices, default=Region.OTHER)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    employee_count = models.PositiveIntegerField(null=True, blank=True)
    industry = models.CharField(max_length=255, blank=True)
    account_stage = models.CharField(max_length=120, blank=True)
    account_owner = models.EmailField(blank=True)
    product_category = models.TextField(blank=True)
    sub_type = models.CharField(max_length=255, blank=True)
    segment = models.CharField(max_length=255, blank=True)
    modality = models.CharField(
        max_length=255,
        blank=True,
        help_text="Comma-separated therapeutic modality focus, e.g. Small Molecules, Biologics, Cell Therapy.",
    )
    priority = models.CharField(max_length=64, blank=True)
    synthego_relation = models.CharField(
        max_length=16,
        choices=SynthegoRelation.choices,
        blank=True,
        help_text="How this company's business relates to Synthego's (CDMO/CRO/Reagents companies only).",
    )
    synthego_relation_notes = models.CharField(max_length=255, blank=True)
    has_marketing_presales_team = models.BooleanField(
        default=False,
        help_text="True if a known contact's department is Marketing, Business Development, Sales Engineering, "
        "or Demand Generation. Derived from existing Person records only.",
    )
    has_data_bi_team = models.BooleanField(
        default=False,
        help_text="True if a known contact's department is Data Warehouse, Data Science, BI, Digital "
        "Transformation, or IT. Derived from existing Person records only.",
    )
    account_list_source = models.CharField(max_length=255, blank=True)
    annual_revenue = models.BigIntegerField(null=True, blank=True)
    funding_data = models.TextField(blank=True)
    revenue_data = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    raw_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["state_code", "city", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "city", "state_code"],
                name="unique_company_city_state",
            )
        ]
        verbose_name_plural = "companies"

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state_code})"

    @property
    def decision_maker_names(self):
        return ", ".join(self.decision_makers.values_list("name", flat=True))

    def as_map_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "domain": self.domain,
            "linkedin_url": self.linkedin_url,
            "logo_url": self.logo_url,
            "address": self.address,
            "city": self.city,
            "state_code": self.state_code,
            "state_name": self.state_name,
            "country": self.country,
            "postal_code": self.postal_code,
            "region": self.region,
            "latitude": float(self.latitude) if self.latitude is not None else None,
            "longitude": float(self.longitude) if self.longitude is not None else None,
            "employee_count": self.employee_count,
            "industry": self.industry,
            "account_stage": self.account_stage,
            "account_owner": self.account_owner,
            "product_category": self.product_category,
            "sub_type": self.sub_type,
            "segment": self.segment,
            "priority": self.priority,
            "account_list_source": self.account_list_source,
            "annual_revenue": self.annual_revenue,
            "is_high_revenue": bool(self.annual_revenue and self.annual_revenue >= 10_000_000),
            "funding_data": self.funding_data,
            "revenue_data": self.revenue_data,
            "notes": self.notes,
            "raw_data": self.raw_data,
            "decision_makers": [maker.as_map_dict() for maker in self.decision_makers.all()],
        }


class DecisionMaker(models.Model):
    company = models.ForeignKey(
        Company,
        related_name="decision_makers",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=255)
    title = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    linkedin_url = models.URLField(blank=True)

    class Meta:
        ordering = ["company__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"],
                name="unique_decision_maker_per_company",
            )
        ]

    def __str__(self):
        if self.title:
            return f"{self.name}, {self.title}"
        return self.name

    def as_map_dict(self):
        return {
            "name": self.name,
            "title": self.title,
            "email": self.email,
            "linkedin_url": self.linkedin_url,
        }


class CompanyLinkedInPost(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="linkedin_posts",
    )

    linkedin_company_id = models.CharField(max_length=255, blank=True)

    post_url = models.URLField(max_length=1000, unique=True)
    post_text = models.TextField(blank=True)
    post_date = models.DateTimeField(null=True, blank=True)

    raw_payload = models.JSONField(default=dict, blank=True)

    is_saved = models.BooleanField(default=False)

    fetched_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-post_date"]
        indexes = [
            models.Index(fields=["company", "-post_date"]),
            models.Index(fields=["-post_date"]),
            models.Index(fields=["is_saved"]),
        ]

    def __str__(self):
        return f"{self.company.name} - {self.post_date or 'No date'}"

# Create your models here.
