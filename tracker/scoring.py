from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import ResourceType, Session, SessionClassification


KNOWN_AI_AGENTS = {
    "gptbot": ("Known GPTBot crawler", 55),
    "chatgpt-user": ("ChatGPT browser-like fetch", 45),
    "claudebot": ("Anthropic Claude crawler", 55),
    "claude-searchbot": ("Anthropic Claude SearchBot", 50),
    "perplexitybot": ("Perplexity crawler", 50),
    "google-extended": ("Google-Extended crawler", 45),
    "bytespider": ("ByteDance crawler", 40),
    "ccbot": ("Common Crawl crawler", 35),
}

AUTOMATION_HINTS = {
    "headless": ("Headless browser hint", 28),
    "playwright": ("Playwright automation hint", 24),
    "selenium": ("Selenium automation hint", 24),
    "puppeteer": ("Puppeteer automation hint", 24),
}

CLOUD_PROVIDERS = {"aws", "amazon", "gcp", "google cloud", "azure", "digitalocean", "linode", "ovh"}


@dataclass
class ScoringResult:
    score: int
    confidence: int
    classification: str
    explanation: str
    signals: list[dict[str, Any]]


def classify_resource_type(path: str, content_type: str = "") -> str:
    lowered_path = (path or "").lower()
    lowered_type = (content_type or "").lower()

    if "text/html" in lowered_type or lowered_path.endswith(("/", ".html", ".htm")):
        return ResourceType.PAGE
    if lowered_path.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")) or lowered_type.startswith("image/"):
        return ResourceType.IMAGE
    if lowered_path.endswith(".js") or "javascript" in lowered_type:
        return ResourceType.SCRIPT
    if lowered_path.endswith(".css") or "text/css" in lowered_type:
        return ResourceType.STYLESHEET
    if lowered_path.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv")):
        return ResourceType.DOCUMENT
    if lowered_path.endswith((".zip", ".tar", ".gz", ".rar", ".7z")):
        return ResourceType.ARCHIVE
    if lowered_type.startswith("video/") or lowered_type.startswith("audio/"):
        return ResourceType.MEDIA
    return ResourceType.OTHER


def score_session(session: Session) -> ScoringResult:
    signals: list[dict[str, Any]] = []
    score = 0

    ua = (session.latest_user_agent or "").lower()
    for token, (label, weight) in KNOWN_AI_AGENTS.items():
        if token in ua:
            signals.append({"signal_type": "known_ai_ua", "label": label, "weight": weight, "evidence": {"token": token}})
            score += weight

    for token, (label, weight) in AUTOMATION_HINTS.items():
        if token in ua:
            signals.append({"signal_type": "automation_ua", "label": label, "weight": weight, "evidence": {"token": token}})
            score += weight

    visitor = session.visitor
    if visitor and visitor.network_provider:
        provider = visitor.network_provider.lower()
        if any(cloud in provider for cloud in CLOUD_PROVIDERS):
            signals.append(
                {
                    "signal_type": "cloud_provider",
                    "label": "Traffic originates from hosting/cloud infrastructure",
                    "weight": 12,
                    "evidence": {"provider": visitor.network_provider},
                }
            )
            score += 12

    request_events = list(session.request_events.all())
    resource_events = list(session.resource_events.all())

    if not session.browser_seen:
        signals.append(
            {
                "signal_type": "no_browser_execution",
                "label": "No browser-side telemetry was observed",
                "weight": 8,
                "evidence": {},
            }
        )
        score += 8

    browser_events = [event for event in request_events if event.source == "browser"]
    if browser_events:
        browser_meta = browser_events[-1].metadata or {}
        capabilities = browser_meta.get("browser_capabilities", {})
        if capabilities.get("webdriver") is True:
            signals.append(
                {
                    "signal_type": "webdriver",
                    "label": "Browser reported webdriver automation",
                    "weight": 35,
                    "evidence": {"webdriver": True},
                }
            )
            score += 35
        if not capabilities.get("languages"):
            signals.append(
                {
                    "signal_type": "missing_languages",
                    "label": "Browser capability signals were incomplete",
                    "weight": 10,
                    "evidence": {"languages": capabilities.get("languages", [])},
                }
            )
            score += 10

    if len(request_events) >= 10:
        duration = max((session.last_seen_at - session.started_at).total_seconds(), 1)
        rpm = len(request_events) / max(duration / 60, 1 / 60)
        if rpm > 45:
            signals.append(
                {
                    "signal_type": "high_velocity",
                    "label": "Request velocity is unusually high",
                    "weight": 18,
                    "evidence": {"requests_per_minute": round(rpm, 2)},
                }
            )
            score += 18

    page_requests = [event for event in resource_events if event.resource_type == ResourceType.PAGE]
    direct_docs = [event for event in resource_events if event.resource_type in {ResourceType.DOCUMENT, ResourceType.ARCHIVE}]
    if direct_docs and not page_requests:
        signals.append(
            {
                "signal_type": "direct_document_access",
                "label": "Documents were accessed without normal page browsing",
                "weight": 18,
                "evidence": {"document_count": len(direct_docs)},
            }
        )
        score += 18

    page_paths = [event.path for event in page_requests]
    if len(page_paths) >= 4 and page_paths == sorted(page_paths):
        signals.append(
            {
                "signal_type": "sequential_traversal",
                "label": "Paths were visited in a sequential crawl-like pattern",
                "weight": 12,
                "evidence": {"paths": page_paths[:5]},
            }
        )
        score += 12

    if score >= 70:
        classification = SessionClassification.KNOWN_AI_CRAWLER if any(
            signal["signal_type"] == "known_ai_ua" for signal in signals
        ) else SessionClassification.SUSPECTED_AI_AGENT
        confidence = min(95, score)
    elif score >= 40:
        classification = SessionClassification.SUSPECTED_AI_AGENT
        confidence = min(85, score)
    elif score >= 20:
        classification = SessionClassification.GENERIC_AUTOMATION
        confidence = min(70, score)
    else:
        classification = SessionClassification.HUMAN if session.browser_seen else SessionClassification.UNKNOWN
        confidence = min(45, max(score, 10 if session.browser_seen else 5))

    if any(signal["signal_type"] == "known_ai_ua" for signal in signals) and len(signals) == 1:
        confidence = min(confidence, 55)

    explanation = " | ".join(signal["label"] for signal in signals[:4]) or "No strong automation signals detected."
    return ScoringResult(score=score, confidence=confidence, classification=classification, explanation=explanation, signals=signals)
