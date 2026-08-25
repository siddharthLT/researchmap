from django.contrib import admin

from .models import Conference, ConferenceCompany, Session, Speaker


class ConferenceCompanyInline(admin.TabularInline):
    model = ConferenceCompany
    extra = 0


class SessionInline(admin.TabularInline):
    model = Session
    extra = 0


@admin.register(Conference)
class ConferenceAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "location", "start_date", "end_date", "company_count", "session_count")
    prepopulated_fields = {"slug": ("name",)}

    def company_count(self, obj):
        return obj.companies.count()

    def session_count(self, obj):
        return obj.sessions.count()


@admin.register(ConferenceCompany)
class ConferenceCompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "conference", "tags", "booth")
    search_fields = ("name", "conference__name")
    autocomplete_fields = ["company"]


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("title", "conference", "day", "start_time", "end_time", "session_type")
    list_filter = ("conference", "session_type", "day")
    search_fields = ("title", "company_name")


@admin.register(Speaker)
class SpeakerAdmin(admin.ModelAdmin):
    list_display = ("name", "title", "company_name", "conference")
    search_fields = ("name", "company_name")
