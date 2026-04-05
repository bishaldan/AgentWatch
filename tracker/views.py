from __future__ import annotations

import csv
import json
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .forms import SessionFilterForm
from .ingest import ingest_browser_event, ingest_request_event, ingest_resource_event
from .models import ResourceAccessEvent, Session, SessionClassification


def _check_ingest_token(request: HttpRequest) -> bool:
    auth_header = request.headers.get("Authorization", "")
    token = request.headers.get("X-Site-Token") or auth_header.removeprefix("Bearer ").strip()
    return token == settings.TRACKER_INGEST_TOKEN


def _parse_payload(request: HttpRequest) -> dict:
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


@dataclass
class TimelineItem:
    kind: str
    occurred_at: object
    title: str
    detail: str
    bytes_served: int


def home(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("tracker:dashboard")
    return redirect("login")


@csrf_exempt
@require_POST
def ingest_browser(request: HttpRequest) -> JsonResponse:
    if not _check_ingest_token(request):
        return JsonResponse({"detail": "Invalid ingest token."}, status=403)
    session = ingest_browser_event(request, _parse_payload(request))
    return JsonResponse({"sessionId": str(session.public_id), "classification": session.classification, "confidence": session.confidence})


@csrf_exempt
@require_POST
def ingest_request(request: HttpRequest) -> JsonResponse:
    if not _check_ingest_token(request):
        return JsonResponse({"detail": "Invalid ingest token."}, status=403)
    session = ingest_request_event(request, _parse_payload(request))
    return JsonResponse({"sessionId": str(session.public_id), "classification": session.classification, "confidence": session.confidence})


@csrf_exempt
@require_POST
def ingest_resource(request: HttpRequest) -> JsonResponse:
    if not _check_ingest_token(request):
        return JsonResponse({"detail": "Invalid ingest token."}, status=403)
    session = ingest_resource_event(request, _parse_payload(request))
    return JsonResponse({"sessionId": str(session.public_id), "classification": session.classification, "confidence": session.confidence})


@login_required
@require_GET
def dashboard(request: HttpRequest) -> HttpResponse:
    sessions = Session.objects.select_related("visitor")
    suspicious = sessions.filter(
        classification__in=[
            SessionClassification.KNOWN_AI_CRAWLER,
            SessionClassification.SUSPECTED_AI_AGENT,
            SessionClassification.GENERIC_AUTOMATION,
        ]
    )
    overview = {
        "total_sessions": sessions.count(),
        "suspicious_sessions": suspicious.count(),
        "known_ai_crawlers": sessions.filter(classification=SessionClassification.KNOWN_AI_CRAWLER).count(),
        "human_sessions": sessions.filter(classification=SessionClassification.HUMAN).count(),
    }
    top_referrers = (
        sessions.exclude(landing_referrer="")
        .values("landing_referrer")
        .annotate(total=Count("id"))
        .order_by("-total")[:5]
    )
    top_paths = (
        ResourceAccessEvent.objects.values("path")
        .annotate(total=Count("id"), bytes_sum=Sum("bytes_served"))
        .order_by("-total")[:8]
    )
    resource_mix = (
        ResourceAccessEvent.objects.values("resource_type")
        .annotate(total=Count("id"))
        .order_by("-total")[:6]
    )
    top_suspicious_sessions = suspicious[:5]
    latest_sessions = sessions[:10]
    context = {
        "overview": overview,
        "top_referrers": top_referrers,
        "top_paths": top_paths,
        "resource_mix": resource_mix,
        "top_suspicious_sessions": top_suspicious_sessions,
        "latest_sessions": latest_sessions,
        "generated_at": timezone.now(),
    }
    return render(request, "tracker/dashboard.html", context)


def _filter_sessions(request: HttpRequest):
    qs = Session.objects.select_related("visitor").prefetch_related("signals")
    form = SessionFilterForm(request.GET or None)
    if form.is_valid():
        classification = form.cleaned_data.get("classification")
        resource_type = form.cleaned_data.get("resource_type")
        referrer = form.cleaned_data.get("referrer")
        date_from = form.cleaned_data.get("date_from")
        date_to = form.cleaned_data.get("date_to")
        if classification:
            qs = qs.filter(classification=classification)
        if resource_type:
            qs = qs.filter(resource_events__resource_type=resource_type).distinct()
        if referrer:
            qs = qs.filter(landing_referrer__icontains=referrer)
        if date_from:
            qs = qs.filter(last_seen_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(last_seen_at__date__lte=date_to)
    return qs, form


@login_required
@require_GET
def session_list(request: HttpRequest) -> HttpResponse:
    qs, form = _filter_sessions(request)
    sessions = qs[:100]
    return render(
        request,
        "tracker/session_list.html",
        {
            "sessions": sessions,
            "form": form,
            "result_count": qs.count(),
        },
    )


def _timeline_for_session(session: Session) -> list[TimelineItem]:
    items: list[TimelineItem] = []
    for event in session.request_events.all():
        method = str((event.metadata or {}).get("method", "GET"))
        items.append(
            TimelineItem(
                kind="request",
                occurred_at=event.occurred_at,
                title=f"{method} {event.path}",
                detail=f"Status {event.status_code} • {event.content_type or 'unknown content'}",
                bytes_served=event.response_bytes,
            )
        )
    for event in session.resource_events.all():
        items.append(
            TimelineItem(
                kind="resource",
                occurred_at=event.occurred_at,
                title=f"{event.get_resource_type_display()} access",
                detail=f"{event.path} • action={event.action}",
                bytes_served=event.bytes_served,
            )
        )
    items.sort(key=lambda item: item.occurred_at)
    return items


@login_required
@require_GET
def session_detail(request: HttpRequest, session_id: str) -> HttpResponse:
    session = get_object_or_404(
        Session.objects.select_related("visitor").prefetch_related("signals", "request_events", "resource_events"),
        public_id=session_id,
    )
    resources = session.resource_events.values("resource_type").annotate(total=Count("id"), bytes_sum=Sum("bytes_served")).order_by("-total")
    totals = session.resource_events.aggregate(total_bytes=Sum("bytes_served"), total_resources=Count("id"))
    context = {
        "session": session,
        "timeline": _timeline_for_session(session),
        "resource_summary": resources,
        "signal_list": session.signals.all(),
        "total_requests": session.request_events.count(),
        "total_resources": totals.get("total_resources") or 0,
        "total_bytes": totals.get("total_bytes") or 0,
    }
    return render(request, "tracker/session_detail.html", context)


@login_required
@require_GET
def session_export_json(request: HttpRequest, session_id: str) -> JsonResponse:
    session = get_object_or_404(Session.objects.select_related("visitor").prefetch_related("signals", "request_events", "resource_events"), public_id=session_id)
    payload = {
        "session": {
            "public_id": str(session.public_id),
            "classification": session.classification,
            "confidence": session.confidence,
            "score": session.latest_score,
            "explanation": session.explanation,
            "landing_path": session.landing_path,
            "landing_referrer": session.landing_referrer,
            "traffic_source": session.traffic_source,
            "started_at": session.started_at.isoformat(),
            "last_seen_at": session.last_seen_at.isoformat(),
        },
        "signals": [
            {
                "signal_type": signal.signal_type,
                "label": signal.label,
                "weight": signal.weight,
                "evidence": signal.evidence,
            }
            for signal in session.signals.all()
        ],
        "requests": [
            {
                "occurred_at": event.occurred_at.isoformat(),
                "path": event.path,
                "status_code": event.status_code,
                "content_type": event.content_type,
                "response_bytes": event.response_bytes,
            }
            for event in session.request_events.all()
        ],
        "resources": [
            {
                "occurred_at": event.occurred_at.isoformat(),
                "path": event.path,
                "resource_type": event.resource_type,
                "bytes_served": event.bytes_served,
                "action": event.action,
            }
            for event in session.resource_events.all()
        ],
    }
    return JsonResponse(payload)


@login_required
@require_GET
def session_export_csv(request: HttpRequest, session_id: str) -> HttpResponse:
    session = get_object_or_404(Session.objects.prefetch_related("resource_events"), public_id=session_id)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="session-{session.public_id}.csv"'
    writer = csv.writer(response)
    writer.writerow(["session_id", "classification", "confidence", "score", "path", "resource_type", "bytes_served", "occurred_at"])
    for event in session.resource_events.all():
        writer.writerow(
            [
                str(session.public_id),
                session.classification,
                session.confidence,
                session.latest_score,
                event.path,
                event.resource_type,
                event.bytes_served,
                event.occurred_at.isoformat(),
            ]
        )
    return response
