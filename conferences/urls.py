from django.urls import path

from . import views

app_name = "conferences"

urlpatterns = [
    path("", views.home, name="home"),
    path("<slug:slug>/", views.conference_detail, name="conference_detail"),
    path("<slug:slug>/export/", views.conference_export, name="conference_export"),
]
