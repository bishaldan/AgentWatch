from django.urls import path

from . import views


urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("sessions/", views.session_list, name="session_list"),
    path("sessions/<uuid:session_id>/", views.session_detail, name="session_detail"),
    path("sessions/<uuid:session_id>/export.json", views.session_export_json, name="session_export_json"),
    path("sessions/<uuid:session_id>/export.csv", views.session_export_csv, name="session_export_csv"),
    path("api/ingest/browser", views.ingest_browser, name="ingest_browser"),
    path("api/ingest/request", views.ingest_request, name="ingest_request"),
    path("api/ingest/resource", views.ingest_resource, name="ingest_resource"),
]
