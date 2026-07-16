from django.contrib import admin

from .models import Company, DecisionMaker


class DecisionMakerInline(admin.TabularInline):
    model = DecisionMaker
    extra = 1


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "domain", "city", "state_code", "country", "annual_revenue", "region")
    list_filter = ("region", "state_code", "country", "city", "product_category", "priority")
    search_fields = (
        "name",
        "domain",
        "city",
        "state_code",
        "state_name",
        "country",
        "address",
        "decision_makers__name",
    )
    inlines = [DecisionMakerInline]


@admin.register(DecisionMaker)
class DecisionMakerAdmin(admin.ModelAdmin):
    list_display = ("name", "title", "company", "email")
    search_fields = ("name", "title", "company__name", "email")

# Register your models here.
