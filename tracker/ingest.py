from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from .models import DetectionSignal, EventSource, RequestEvent, ResourceAccessEvent, Session, SessionRiskScore, VisitorIdentity
from .scoring import classify_resource_type, score_session
from .utils import first_non_empty, stable_hash


@dataclass
class IngestContext:
    ip_address: str
    site_id: str


def extract_client_ip(request: HttpRequest) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def fingerprint_request(headers: dict[str, Any], ip_address: str, user_agent: str) -> str:
    accept = str(headers.get("accept", ""))
    language = str(headers.get("accept-language", ""))
    return stable_hash(ip_address, user_agent, accept, language)


def normalize_headers(raw_headers: dict[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in (raw_headers or {}).items():
        normalized[str(key).lower()] = str(value)
    return normalized


def resolve_context(request: HttpRequest, payload: dict[str, Any]) -> IngestContext:
    return IngestContext(
        ip_address=extract_client_ip(request),
        site_id=str(payload.get("siteId") or settings.TRACKER_SITE_ID),
    )


def get_or_create_visitor(
    *,
    ip_address: str,
    user_agent: str,
    fingerprint: str,
    geo_country: str = "",
    network_asn: str = "",
    network_provider: str = "",
) -> VisitorIdentity:
    hashed_ip = stable_hash(ip_address)
    user_agent_hash = stable_hash(user_agent)
    visitor, _ = VisitorIdentity.objects.get_or_create(
        network_fingerprint=fingerprint,
        defaults={
            "hashed_ip": hashed_ip,
            "user_agent_hash": user_agent_hash,
            "raw_ip": ip_address or None,
            "geo_country": geo_country,
            "network_asn": network_asn,
            "network_provider": network_provider,
        },
    )
    visitor.hashed_ip = hashed_ip
    visitor.user_agent_hash = user_agent_hash
    if ip_address:
        visitor.raw_ip = ip_address
    visitor.geo_country = geo_country or visitor.geo_country
    visitor.network_asn = network_asn or visitor.network_asn
    visitor.network_provider = network_provider or visitor.network_provider
    visitor.last_seen_at = timezone.now()
    visitor.save(update_fields=["hashed_ip", "user_agent_hash", "raw_ip", "geo_country", "network_asn", "network_provider", "last_seen_at", "updated_at"])
    return visitor


def derive_session_key(payload: dict[str, Any], fingerprint: str) -> str:
    return str(payload.get("sessionId") or payload.get("session_id") or fingerprint[:24])


def resolve_traffic_source(referrer: str, utm_source: str) -> str:
    if utm_source:
        return utm_source
    if not referrer:
        return "direct"
    if "google." in referrer:
        return "search"
    if "facebook." in referrer or "twitter." in referrer or "x.com" in referrer:
        return "social"
    return "referral"


def upsert_session(
    *,
    payload: dict[str, Any],
    context: IngestContext,
    visitor: VisitorIdentity,
    source: str,
    user_agent: str,
) -> Session:
    session_key = derive_session_key(payload, visitor.network_fingerprint)
    now = timezone.now()
    session, created = Session.objects.get_or_create(
        site_id=context.site_id,
        session_key=session_key,
        defaults={
            "visitor": visitor,
            "landing_path": payload.get("path", "")[:512],
            "landing_referrer": payload.get("referrer", "")[:1024],
            "traffic_source": resolve_traffic_source(payload.get("referrer", ""), payload.get("utmSource", "")),
            "latest_user_agent": user_agent,
            "source": source,
            "started_at": now,
            "last_seen_at": now,
            "browser_seen": source == EventSource.BROWSER,
            "request_only": source != EventSource.BROWSER,
        },
    )
    if not created:
        session.visitor = visitor
        session.last_seen_at = now
        session.latest_user_agent = user_agent or session.latest_user_agent
        session.source = source if source == EventSource.BROWSER or session.source == EventSource.ORIGIN else session.source
        session.browser_seen = session.browser_seen or source == EventSource.BROWSER
        session.request_only = not session.browser_seen
        if not session.landing_path and payload.get("path"):
            session.landing_path = str(payload["path"])[:512]
        if not session.landing_referrer and payload.get("referrer"):
            session.landing_referrer = str(payload["referrer"])[:1024]
        if not session.traffic_source:
            session.traffic_source = resolve_traffic_source(payload.get("referrer", ""), payload.get("utmSource", ""))
        session.save()
    return session


def persist_scoring(session: Session) -> None:
    result = score_session(session)
    DetectionSignal.objects.filter(session=session).delete()
    DetectionSignal.objects.bulk_create(
        [
            DetectionSignal(
                session=session,
                signal_type=signal["signal_type"],
                label=signal["label"],
                weight=signal["weight"],
                evidence=signal.get("evidence", {}),
            )
            for signal in result.signals
        ]
    )
    session.classification = result.classification
    session.confidence = result.confidence
    session.latest_score = result.score
    session.explanation = result.explanation
    session.save(update_fields=["classification", "confidence", "latest_score", "explanation", "updated_at"])
    SessionRiskScore.objects.update_or_create(
        session=session,
        defaults={
            "score": result.score,
            "confidence": result.confidence,
            "classification": result.classification,
            "explanation": result.explanation,
        },
    )


@transaction.atomic
def ingest_browser_event(request: HttpRequest, payload: dict[str, Any]) -> Session:
    context = resolve_context(request, payload)
    headers = normalize_headers(payload.get("headers", {}))
    user_agent = first_non_empty([payload.get("userAgent"), request.META.get("HTTP_USER_AGENT")])
    fingerprint = fingerprint_request(headers, context.ip_address, user_agent)
    visitor = get_or_create_visitor(
        ip_address=context.ip_address,
        user_agent=user_agent,
        fingerprint=fingerprint,
        geo_country=str(payload.get("geoCountry", "")),
        network_asn=str(payload.get("networkAsn", "")),
        network_provider=str(payload.get("networkProvider", "")),
    )
    session = upsert_session(payload=payload, context=context, visitor=visitor, source=EventSource.BROWSER, user_agent=user_agent)
    metadata = {
        "event_type": payload.get("eventType", "page_view"),
        "browser_capabilities": payload.get("browserCapabilities", {}),
        "screen": payload.get("screen", {}),
        "timezone": payload.get("timezone", ""),
    }
    RequestEvent.objects.create(
        session=session,
        visitor=visitor,
        source=EventSource.BROWSER,
        path=str(payload.get("path", "/"))[:1024],
        query_string=str(payload.get("query", "")),
        status_code=200,
        response_bytes=0,
        content_type="text/html",
        referrer=str(payload.get("referrer", ""))[:1024],
        user_agent=user_agent,
        is_page_view=True,
        request_headers=headers,
        metadata=metadata,
    )
    persist_scoring(session)
    return session


@transaction.atomic
def ingest_request_event(request: HttpRequest, payload: dict[str, Any]) -> Session:
    context = resolve_context(request, payload)
    headers = normalize_headers(payload.get("headers", {}))
    user_agent = first_non_empty([payload.get("userAgent"), headers.get("user-agent"), request.META.get("HTTP_USER_AGENT")])
    fingerprint = fingerprint_request(headers, context.ip_address, user_agent)
    visitor = get_or_create_visitor(
        ip_address=context.ip_address,
        user_agent=user_agent,
        fingerprint=fingerprint,
        geo_country=str(payload.get("geoCountry", "")),
        network_asn=str(payload.get("networkAsn", "")),
        network_provider=str(payload.get("networkProvider", "")),
    )
    session = upsert_session(payload=payload, context=context, visitor=visitor, source=EventSource.ORIGIN, user_agent=user_agent)
    request_event = RequestEvent.objects.create(
        session=session,
        visitor=visitor,
        source=EventSource.ORIGIN,
        method=str(payload.get("method", "GET"))[:16],
        path=str(payload.get("path", "/"))[:1024],
        query_string=str(payload.get("query", "")),
        status_code=int(payload.get("statusCode", 200)),
        response_bytes=int(payload.get("responseBytes", 0)),
        content_type=str(payload.get("contentType", ""))[:255],
        referrer=str(payload.get("referrer", ""))[:1024],
        user_agent=user_agent,
        is_page_view=str(payload.get("contentType", "")).startswith("text/html"),
        request_headers=headers,
        metadata={"method": payload.get("method", "GET"), "raw": payload.get("metadata", {})},
    )
    ResourceAccessEvent.objects.create(
        session=session,
        request_event=request_event,
        source=EventSource.ORIGIN,
        path=request_event.path,
        full_url=str(payload.get("url", ""))[:2048],
        resource_type=classify_resource_type(request_event.path, request_event.content_type),
        content_type=request_event.content_type,
        bytes_served=request_event.response_bytes,
        action="served",
        metadata={"status_code": request_event.status_code},
    )
    persist_scoring(session)
    return session


@transaction.atomic
def ingest_resource_event(request: HttpRequest, payload: dict[str, Any]) -> Session:
    context = resolve_context(request, payload)
    headers = normalize_headers(payload.get("headers", {}))
    user_agent = first_non_empty([payload.get("userAgent"), request.META.get("HTTP_USER_AGENT")])
    fingerprint = fingerprint_request(headers, context.ip_address, user_agent)
    visitor = get_or_create_visitor(
        ip_address=context.ip_address,
        user_agent=user_agent,
        fingerprint=fingerprint,
    )
    session = upsert_session(payload=payload, context=context, visitor=visitor, source=EventSource.BROWSER, user_agent=user_agent)
    resources = payload.get("resources", [])
    if isinstance(resources, str):
        resources = json.loads(resources)
    for resource in resources:
        path = str(resource.get("path") or resource.get("name") or resource.get("url") or "/")[:1024]
        content_type = str(resource.get("contentType", ""))[:255]
        ResourceAccessEvent.objects.create(
            session=session,
            source=EventSource.BROWSER,
            path=path,
            full_url=str(resource.get("url", ""))[:2048],
            resource_type=str(resource.get("resourceType") or classify_resource_type(path, content_type)),
            content_type=content_type,
            bytes_served=int(resource.get("transferSize") or resource.get("bytesServed") or 0),
            action=str(resource.get("action", "observed")),
            metadata=resource,
        )
    persist_scoring(session)
    return session


def prune_old_data() -> dict[str, int]:
    now = timezone.now()
    raw_cutoff = now - timedelta(days=settings.TRACKER_RAW_RETENTION_DAYS)
    aggregate_cutoff = now - timedelta(days=settings.TRACKER_AGGREGATE_RETENTION_DAYS)

    deleted_request_events, _ = RequestEvent.objects.filter(occurred_at__lt=raw_cutoff).delete()
    deleted_resource_events, _ = ResourceAccessEvent.objects.filter(occurred_at__lt=raw_cutoff).delete()
    VisitorIdentity.objects.filter(last_seen_at__lt=aggregate_cutoff, sessions__isnull=True).delete()

    stale_sessions = Session.objects.filter(last_seen_at__lt=aggregate_cutoff)
    deleted_sessions, _ = stale_sessions.delete()

    VisitorIdentity.objects.filter(raw_ip__isnull=False, last_seen_at__lt=raw_cutoff).update(raw_ip=None)

    return {
        "request_events_deleted": deleted_request_events,
        "resource_events_deleted": deleted_resource_events,
        "sessions_deleted": deleted_sessions,
    }
