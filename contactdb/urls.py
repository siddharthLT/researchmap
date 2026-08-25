from django.urls import path

from . import views

app_name = "contactdb"

urlpatterns = [
    path("", views.home, name="home"),
    path("companies/<slug:slug>/", views.company_list_detail, name="company_list_detail"),
    path("people/<slug:slug>/", views.person_list_detail, name="person_list_detail"),
]
