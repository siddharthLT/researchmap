from django.urls import path

from . import views

app_name = "contactdb"

urlpatterns = [
    path("", views.home, name="home"),
    path("companies/<slug:slug>/", views.company_list_detail, name="company_list_detail"),
    path("people/<slug:slug>/", views.person_list_detail, name="person_list_detail"),
    path("connections/<slug:slug>/", views.connection_universe, name="connection_universe"),
    path("company/<int:company_id>/", views.company_brief, name="company_brief"),
    path("api/people/<int:person_id>/contact/", views.person_contact, name="person_contact"),
]
