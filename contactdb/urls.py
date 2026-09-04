from django.urls import path

from . import views

app_name = "contactdb"

urlpatterns = [
    path("", views.home, name="home"),
    path("companies/<slug:slug>/", views.company_list_detail, name="company_list_detail"),
    path("companies/<slug:slug>/add/", views.company_list_add, name="company_list_add"),
    path("companies/<slug:slug>/remove/<int:company_id>/", views.company_list_remove, name="company_list_remove"),
    path("people/<slug:slug>/", views.person_list_detail, name="person_list_detail"),
    path("people/<slug:slug>/add/", views.person_list_add, name="person_list_add"),
    path("people/<slug:slug>/remove/<int:person_id>/", views.person_list_remove, name="person_list_remove"),
    path("connections/<slug:slug>/", views.connection_universe, name="connection_universe"),
    path("company/<int:company_id>/", views.company_brief, name="company_brief"),
    path("api/people/<int:person_id>/contact/", views.person_contact, name="person_contact"),
    path("outreach-plan/", views.outreach_plan, name="outreach_plan"),
]
