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
