from django.urls import path

from . import views

app_name = "conferences"

urlpatterns = [
    path("", views.home, name="home"),
    path("<slug:slug>/", views.conference_detail, name="conference_detail"),
]
