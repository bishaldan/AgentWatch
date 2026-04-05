from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import ResourceAccessEvent, Session, SessionClassification


@override_settings(TRACKER_INGEST_TOKEN="test-token", STATICFILES_DIRS=[])
class TrackerTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="operator@example.com",
            email="operator@example.com",
            password="StrongPassword123",
        )

    def test_ingest_rejects_invalid_token(self):
        response = self.client.post(
            reverse("tracker:ingest_request"),
            data='{"path": "/secret.pdf"}',
            content_type="application/json",
            HTTP_X_SITE_TOKEN="wrong",
        )
        self.assertEqual(response.status_code, 403)

    def test_known_ai_crawler_is_classified(self):
        response = self.client.post(
            reverse("tracker:ingest_request"),
            data="""
            {
              "siteId": "publisher-site",
              "sessionId": "crawler-1",
              "path": "/docs/pricing.pdf",
              "contentType": "application/pdf",
              "responseBytes": 2048,
              "userAgent": "Mozilla/5.0 GPTBot/1.0",
              "headers": {"accept": "text/html"}
            }
            """,
            content_type="application/json",
            HTTP_X_SITE_TOKEN="test-token",
            REMOTE_ADDR="203.0.113.10",
        )
        self.assertEqual(response.status_code, 200)
        session = Session.objects.get(session_key="crawler-1")
        self.assertEqual(session.classification, SessionClassification.KNOWN_AI_CRAWLER)
        self.assertGreaterEqual(session.confidence, 70)

    def test_spoofed_ua_without_supporting_signals_is_not_overclassified(self):
        self.client.post(
            reverse("tracker:ingest_browser"),
            data="""
            {
              "siteId": "publisher-site",
              "sessionId": "spoofed-1",
              "path": "/",
              "userAgent": "Mozilla/5.0 GPTBot/1.0",
              "browserCapabilities": {"webdriver": false, "languages": ["en-US"]},
              "headers": {"accept": "text/html"}
            }
            """,
            content_type="application/json",
            HTTP_X_SITE_TOKEN="test-token",
            REMOTE_ADDR="203.0.113.12",
        )
        session = Session.objects.get(session_key="spoofed-1")
        self.assertEqual(session.classification, SessionClassification.SUSPECTED_AI_AGENT)
        self.assertLessEqual(session.confidence, 55)

    def test_browser_and_origin_events_merge_same_session(self):
        browser_payload = """
        {
          "siteId": "publisher-site",
          "sessionId": "merge-1",
          "path": "/pricing",
          "referrer": "https://google.com/search",
          "userAgent": "Mozilla/5.0",
          "browserCapabilities": {"webdriver": false, "languages": ["en-US"]},
          "headers": {"accept": "text/html"}
        }
        """
        request_payload = """
        {
          "siteId": "publisher-site",
          "sessionId": "merge-1",
          "path": "/pricing",
          "contentType": "text/html",
          "responseBytes": 512,
          "statusCode": 200,
          "userAgent": "Mozilla/5.0",
          "headers": {"accept": "text/html"}
        }
        """
        self.client.post(reverse("tracker:ingest_browser"), data=browser_payload, content_type="application/json", HTTP_X_SITE_TOKEN="test-token", REMOTE_ADDR="203.0.113.11")
        self.client.post(reverse("tracker:ingest_request"), data=request_payload, content_type="application/json", HTTP_X_SITE_TOKEN="test-token", REMOTE_ADDR="203.0.113.11")
        session = Session.objects.get(session_key="merge-1")
        self.assertEqual(session.request_events.count(), 2)
        self.assertEqual(session.resource_events.count(), 1)
        self.assertTrue(session.browser_seen)

    def test_webdriver_browser_becomes_suspected_agent(self):
        response = self.client.post(
            reverse("tracker:ingest_browser"),
            data="""
            {
              "siteId": "publisher-site",
              "sessionId": "browser-bot",
              "path": "/",
              "userAgent": "Mozilla/5.0 HeadlessChrome",
              "browserCapabilities": {"webdriver": true, "languages": []},
              "headers": {"accept": "text/html"}
            }
            """,
            content_type="application/json",
            HTTP_X_SITE_TOKEN="test-token",
            REMOTE_ADDR="198.51.100.4",
        )
        self.assertEqual(response.status_code, 200)
        session = Session.objects.get(session_key="browser-bot")
        self.assertEqual(session.classification, SessionClassification.SUSPECTED_AI_AGENT)

    def test_human_browser_session_stays_human(self):
        self.client.post(
            reverse("tracker:ingest_browser"),
            data="""
            {
              "siteId": "publisher-site",
              "sessionId": "human-1",
              "path": "/about",
              "userAgent": "Mozilla/5.0 Safari",
              "browserCapabilities": {"webdriver": false, "languages": ["en-US", "en"]},
              "headers": {"accept": "text/html"}
            }
            """,
            content_type="application/json",
            HTTP_X_SITE_TOKEN="test-token",
            REMOTE_ADDR="198.51.100.9",
        )
        session = Session.objects.get(session_key="human-1")
        self.assertEqual(session.classification, SessionClassification.HUMAN)

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("tracker:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_export_json_contains_resources(self):
        session = Session.objects.create(site_id="publisher-site", session_key="export-me")
        ResourceAccessEvent.objects.create(session=session, path="/report.pdf", resource_type="document", bytes_served=333, action="served")
        self.client.login(username="operator@example.com", password="StrongPassword123")
        response = self.client.get(reverse("tracker:session_export_json", args=[session.public_id]))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["resources"][0]["path"], "/report.pdf")
