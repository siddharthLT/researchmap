from django.urls import path

from . import views


app_name = "companymap"

urlpatterns = [
    path("", views.map_view, name="map"),
    path("api/companies/", views.company_map_data, name="company_map_data"),
    path("api/chat/", views.chat_api, name="chat_api"),
]
