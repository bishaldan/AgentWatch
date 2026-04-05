from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class SessionClassification(models.TextChoices):
    HUMAN = "human", "Human"
    KNOWN_AI_CRAWLER = "known_ai_crawler", "Known AI crawler"
    SUSPECTED_AI_AGENT = "suspected_ai_agent", "Suspected AI agent"
    GENERIC_AUTOMATION = "generic_automation", "Generic automation"
    UNKNOWN = "unknown", "Unknown"


class ResourceType(models.TextChoices):
    PAGE = "page", "Page"
    IMAGE = "image", "Image"
    SCRIPT = "script", "Script"
    STYLESHEET = "stylesheet", "Stylesheet"
    DOCUMENT = "document", "Document"
    ARCHIVE = "archive", "Archive"
    MEDIA = "media", "Media"
    OTHER = "other", "Other"


class EventSource(models.TextChoices):
    BROWSER = "browser", "Browser"
    ORIGIN = "origin", "Origin"
    SYSTEM = "system", "System"


class VisitorIdentity(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    hashed_ip = models.CharField(max_length=128, db_index=True)
    user_agent_hash = models.CharField(max_length=128, blank=True)
    network_fingerprint = models.CharField(max_length=128, db_index=True)
    raw_ip = models.GenericIPAddressField(null=True, blank=True)
    geo_country = models.CharField(max_length=64, blank=True)
    network_asn = models.CharField(max_length=64, blank=True)
    network_provider = models.CharField(max_length=128, blank=True)
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.network_fingerprint[:10]}..."


class Session(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    visitor = models.ForeignKey(
        VisitorIdentity,
        related_name="sessions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    site_id = models.CharField(max_length=128, db_index=True)
    session_key = models.CharField(max_length=128, db_index=True)
    landing_path = models.CharField(max_length=512, blank=True)
    landing_referrer = models.CharField(max_length=1024, blank=True)
    traffic_source = models.CharField(max_length=256, blank=True)
    latest_user_agent = models.TextField(blank=True)
    source = models.CharField(max_length=16, choices=EventSource.choices, default=EventSource.ORIGIN)
    classification = models.CharField(
        max_length=32,
        choices=SessionClassification.choices,
        default=SessionClassification.UNKNOWN,
        db_index=True,
    )
    confidence = models.PositiveSmallIntegerField(default=0)
    latest_score = models.PositiveSmallIntegerField(default=0)
    explanation = models.TextField(blank=True)
    browser_seen = models.BooleanField(default=False)
    request_only = models.BooleanField(default=True)
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_seen_at"]
        indexes = [
            models.Index(fields=["site_id", "classification"]),
            models.Index(fields=["site_id", "last_seen_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.site_id}:{self.session_key}"


class RequestEvent(models.Model):
    session = models.ForeignKey(Session, related_name="request_events", on_delete=models.CASCADE)
    visitor = models.ForeignKey(
        VisitorIdentity,
        related_name="request_events",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    source = models.CharField(max_length=16, choices=EventSource.choices, default=EventSource.ORIGIN)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    method = models.CharField(max_length=16, default="GET")
    path = models.CharField(max_length=1024, db_index=True)
    query_string = models.TextField(blank=True)
    status_code = models.PositiveSmallIntegerField(default=200)
    response_bytes = models.PositiveIntegerField(default=0)
    content_type = models.CharField(max_length=255, blank=True)
    referrer = models.CharField(max_length=1024, blank=True)
    user_agent = models.TextField(blank=True)
    is_page_view = models.BooleanField(default=False)
    request_headers = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["occurred_at", "id"]


class ResourceAccessEvent(models.Model):
    session = models.ForeignKey(Session, related_name="resource_events", on_delete=models.CASCADE)
    request_event = models.ForeignKey(
        RequestEvent,
        related_name="resource_events",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    source = models.CharField(max_length=16, choices=EventSource.choices, default=EventSource.BROWSER)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    path = models.CharField(max_length=1024, db_index=True)
    full_url = models.CharField(max_length=2048, blank=True)
    resource_type = models.CharField(max_length=32, choices=ResourceType.choices, default=ResourceType.OTHER)
    content_type = models.CharField(max_length=255, blank=True)
    bytes_served = models.PositiveIntegerField(default=0)
    action = models.CharField(max_length=64, default="served")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["occurred_at", "id"]


class DetectionSignal(models.Model):
    session = models.ForeignKey(Session, related_name="signals", on_delete=models.CASCADE)
    signal_type = models.CharField(max_length=128, db_index=True)
    label = models.CharField(max_length=255)
    weight = models.SmallIntegerField(default=0)
    evidence = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-weight", "id"]


class SessionRiskScore(models.Model):
    session = models.OneToOneField(Session, related_name="risk_score", on_delete=models.CASCADE)
    score = models.PositiveSmallIntegerField(default=0)
    confidence = models.PositiveSmallIntegerField(default=0)
    classification = models.CharField(
        max_length=32,
        choices=SessionClassification.choices,
        default=SessionClassification.UNKNOWN,
    )
    explanation = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.classification}:{self.score}"
