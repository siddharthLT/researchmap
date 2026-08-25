from django.db import models
from django.utils.text import slugify


class Conference(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    location = models.CharField(max_length=255, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    source_file = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class ConferenceCompany(models.Model):
    class Tag(models.TextChoices):
        SPEAKER_SESSION = "speaker_session", "Speaker Session"
        POSTER_SESSION = "poster_session", "Poster Session"
        EXHIBITOR = "exhibitor", "Exhibitor"
        NETWORKING_SESSION = "networking_session", "Networking Session"

    conference = models.ForeignKey(Conference, related_name="companies", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    tags = models.JSONField(default=list, blank=True, help_text="List of ConferenceCompany.Tag values.")
    booth = models.CharField(max_length=64, blank=True)
    website = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    company = models.ForeignKey(
        "companymap.Company",
        related_name="conference_appearances",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Optional link to the matching company in the main map database.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "companies"
        constraints = [
            models.UniqueConstraint(fields=["conference", "name"], name="unique_company_per_conference"),
        ]

    def __str__(self):
        return f"{self.name} @ {self.conference.name}"


class Speaker(models.Model):
    conference = models.ForeignKey(Conference, related_name="speakers", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    title = models.CharField(max_length=255, blank=True)
    company_name = models.CharField(max_length=255, blank=True)
    profile_url = models.URLField(blank=True)
    photo_url = models.URLField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Session(models.Model):
    class SessionType(models.TextChoices):
        KEYNOTE = "keynote", "Keynote"
        PANEL = "panel", "Panel Discussion"
        WORKSHOP = "workshop", "Workshop"
        NETWORKING = "networking", "Networking"
        MEAL = "meal", "Meal / Social"
        LOGISTICS = "logistics", "Logistics"
        EXHIBITOR_PRESENTATION = "exhibitor_presentation", "Exhibitor Presentation"
        OTHER = "other", "Other"

    conference = models.ForeignKey(Conference, related_name="sessions", on_delete=models.CASCADE)
    title = models.CharField(max_length=500)
    session_type = models.CharField(max_length=24, choices=SessionType.choices, default=SessionType.OTHER)
    day = models.DateField(null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    raw_time_label = models.CharField(max_length=64, blank=True)
    description = models.TextField(blank=True)
    speakers = models.JSONField(default=list, blank=True, help_text="List of {name, affiliation} dicts.")
    company_name = models.CharField(
        max_length=255, blank=True, help_text="Presenting company, for exhibitor-presentation sessions."
    )
    location = models.CharField(max_length=255, blank=True)
    source_sheet = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["day", "start_time", "id"]

    def __str__(self):
        return f"{self.title} ({self.day})"
