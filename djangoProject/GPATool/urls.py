from django.urls import path
from .views import login_view, fetch_gpa_page, fetch_gpa_view

urlpatterns = [
    path("", login_view, name="login"),
    path("fetch_gpa/", fetch_gpa_page, name="fetch_gpa_page"),
    path("fetch_gpa/stream/", fetch_gpa_view, name="fetch_gpa_stream"),
]
