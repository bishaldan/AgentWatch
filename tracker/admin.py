from django.contrib import admin

from .models import DetectionSignal, RequestEvent, ResourceAccessEvent, Session, SessionRiskScore, VisitorIdentity


@admin.register(VisitorIdentity)
class VisitorIdentityAdmin(admin.ModelAdmin):
    list_display = ("network_fingerprint", "geo_country", "network_provider", "last_seen_at")
    search_fields = ("network_fingerprint", "hashed_ip", "network_provider")


class DetectionSignalInline(admin.TabularInline):
    model = DetectionSignal
    extra = 0
    readonly_fields = ("signal_type", "label", "weight", "evidence", "created_at")


class SessionRiskInline(admin.StackedInline):
    model = SessionRiskScore
    extra = 0
    readonly_fields = ("score", "confidence", "classification", "explanation", "updated_at")


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("session_key", "classification", "confidence", "latest_score", "last_seen_at")
    list_filter = ("classification", "source", "browser_seen")
    search_fields = ("session_key", "landing_path", "landing_referrer", "latest_user_agent")
    inlines = [SessionRiskInline, DetectionSignalInline]


@admin.register(RequestEvent)
class RequestEventAdmin(admin.ModelAdmin):
    list_display = ("session", "path", "status_code", "response_bytes", "occurred_at")
    list_filter = ("source", "status_code", "is_page_view")
    search_fields = ("path", "content_type", "user_agent")


@admin.register(ResourceAccessEvent)
class ResourceAccessEventAdmin(admin.ModelAdmin):
    list_display = ("session", "resource_type", "path", "bytes_served", "occurred_at")
    list_filter = ("source", "resource_type", "action")
    search_fields = ("path", "content_type")


@admin.register(DetectionSignal)
class DetectionSignalAdmin(admin.ModelAdmin):
    list_display = ("session", "signal_type", "weight", "created_at")
    list_filter = ("signal_type",)
    search_fields = ("label",)


@admin.register(SessionRiskScore)
class SessionRiskScoreAdmin(admin.ModelAdmin):
    list_display = ("session", "classification", "score", "confidence", "updated_at")
    list_filter = ("classification",)
