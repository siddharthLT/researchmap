from django.urls import path

from . import views


app_name = "companymap"

urlpatterns = [
    path("", views.map_view, name="map"),
    path("api/companies/", views.company_map_data, name="company_map_data"),
    path("api/chat/", views.chat_api, name="chat_api"),
    path("company/<int:company_id>/pin/", views.company_pin_map, name="company_pin_map"),
    path("social-room/", views.social_room, name="social_room"),
    path("social-room/save/<int:post_id>/", views.social_room_toggle_save, name="social_room_toggle_save"),
]
