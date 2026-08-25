from django.contrib import admin

from .models import CompanyBrief, CompanyList, CompanyListItem, Person, PersonList, PersonListItem


class CompanyListItemInline(admin.TabularInline):
    model = CompanyListItem
    extra = 1
    autocomplete_fields = ["company"]


@admin.register(CompanyList)
class CompanyListAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "company_count", "updated_at")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [CompanyListItemInline]

    def company_count(self, obj):
        return obj.items.count()


class PersonListItemInline(admin.TabularInline):
    model = PersonListItem
    extra = 1
    autocomplete_fields = ["person"]


@admin.register(PersonList)
class PersonListAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "person_count", "updated_at")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [PersonListItemInline]

    def person_count(self, obj):
        return obj.items.count()


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("name", "title", "display_company", "email")
    search_fields = ("name", "title", "email", "company__name", "company_name")


@admin.register(CompanyBrief)
class CompanyBriefAdmin(admin.ModelAdmin):
    list_display = ("company", "source_document", "updated_at")
    search_fields = ("company__name", "source_document")
    autocomplete_fields = ["company"]
