from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import request as urllib_request

@dataclass
class PublisherRequestReporter:
    collector_url: str
    site_id: str
    token: str
    timeout: float = 2.0

    def _post(self, endpoint: str, payload: dict[str, Any]) -> None:
        req = urllib_request.Request(
            url=f"{self.collector_url.rstrip('/')}{endpoint}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Site-Token": self.token,
            },
            method="POST",
        )
        with urllib_request.urlopen(req, timeout=self.timeout):
            return

    def send_request_event(
        self,
        *,
        path: str,
        content_type: str,
        response_bytes: int,
        status_code: int = 200,
        method: str = "GET",
        query: str = "",
        referrer: str = "",
        user_agent: str = "",
        session_id: str = "",
        url: str = "",
        headers: dict[str, str] | None = None,
        network_provider: str = "",
        network_asn: str = "",
        geo_country: str = "",
    ) -> None:
        payload = {
            "siteId": self.site_id,
            "sessionId": session_id,
            "path": path,
            "contentType": content_type,
            "responseBytes": response_bytes,
            "statusCode": status_code,
            "method": method,
            "query": query,
            "referrer": referrer,
            "userAgent": user_agent,
            "url": url,
            "headers": headers or {},
            "networkProvider": network_provider,
            "networkAsn": network_asn,
            "geoCountry": geo_country,
        }
        self._post("/api/ingest/request", payload)


class DjangoOriginReporterMiddleware:
    """
    Example middleware for a publisher-managed Django app.

    Configure with:
      AGENT_REPORTER_COLLECTOR_URL
      AGENT_REPORTER_SITE_ID
      AGENT_REPORTER_TOKEN
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, django_request):
        from django.conf import settings

        response = self.get_response(django_request)
        collector_url = getattr(settings, "AGENT_REPORTER_COLLECTOR_URL", "")
        site_id = getattr(settings, "AGENT_REPORTER_SITE_ID", "")
        token = getattr(settings, "AGENT_REPORTER_TOKEN", "")
        if collector_url and site_id and token:
            reporter = PublisherRequestReporter(collector_url=collector_url, site_id=site_id, token=token)
            reporter.send_request_event(
                path=django_request.path,
                content_type=response.get("Content-Type", ""),
                response_bytes=len(getattr(response, "content", b"") or b""),
                status_code=response.status_code,
                method=django_request.method,
                query=django_request.META.get("QUERY_STRING", ""),
                referrer=django_request.META.get("HTTP_REFERER", ""),
                user_agent=django_request.META.get("HTTP_USER_AGENT", ""),
                session_id=django_request.COOKIES.get("ai_agent_session", ""),
                url=django_request.build_absolute_uri(),
                headers={"accept": django_request.META.get("HTTP_ACCEPT", "")},
            )
        return response
