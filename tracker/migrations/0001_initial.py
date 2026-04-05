from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="VisitorIdentity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("hashed_ip", models.CharField(db_index=True, max_length=128)),
                ("user_agent_hash", models.CharField(blank=True, max_length=128)),
                ("network_fingerprint", models.CharField(db_index=True, max_length=128)),
                ("raw_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("geo_country", models.CharField(blank=True, max_length=64)),
                ("network_asn", models.CharField(blank=True, max_length=64)),
                ("network_provider", models.CharField(blank=True, max_length=128)),
                ("first_seen_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("last_seen_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="Session",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ("site_id", models.CharField(db_index=True, max_length=128)),
                ("session_key", models.CharField(db_index=True, max_length=128)),
                ("landing_path", models.CharField(blank=True, max_length=512)),
                ("landing_referrer", models.CharField(blank=True, max_length=1024)),
                ("traffic_source", models.CharField(blank=True, max_length=256)),
                ("latest_user_agent", models.TextField(blank=True)),
                ("source", models.CharField(choices=[("browser", "Browser"), ("origin", "Origin"), ("system", "System")], default="origin", max_length=16)),
                ("classification", models.CharField(choices=[("human", "Human"), ("known_ai_crawler", "Known AI crawler"), ("suspected_ai_agent", "Suspected AI agent"), ("generic_automation", "Generic automation"), ("unknown", "Unknown")], db_index=True, default="unknown", max_length=32)),
                ("confidence", models.PositiveSmallIntegerField(default=0)),
                ("latest_score", models.PositiveSmallIntegerField(default=0)),
                ("explanation", models.TextField(blank=True)),
                ("browser_seen", models.BooleanField(default=False)),
                ("request_only", models.BooleanField(default=True)),
                ("started_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("last_seen_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("visitor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sessions", to="tracker.visitoridentity")),
            ],
            options={"ordering": ["-last_seen_at"]},
        ),
        migrations.AddIndex(
            model_name="session",
            index=models.Index(fields=["site_id", "classification"], name="tracker_sess_site_id_6dc1e9_idx"),
        ),
        migrations.AddIndex(
            model_name="session",
            index=models.Index(fields=["site_id", "last_seen_at"], name="tracker_sess_site_id_1a2fd2_idx"),
        ),
        migrations.CreateModel(
            name="SessionRiskScore",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("score", models.PositiveSmallIntegerField(default=0)),
                ("confidence", models.PositiveSmallIntegerField(default=0)),
                ("classification", models.CharField(choices=[("human", "Human"), ("known_ai_crawler", "Known AI crawler"), ("suspected_ai_agent", "Suspected AI agent"), ("generic_automation", "Generic automation"), ("unknown", "Unknown")], default="unknown", max_length=32)),
                ("explanation", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("session", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="risk_score", to="tracker.session")),
            ],
        ),
        migrations.CreateModel(
            name="RequestEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(choices=[("browser", "Browser"), ("origin", "Origin"), ("system", "System")], default="origin", max_length=16)),
                ("occurred_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("method", models.CharField(default="GET", max_length=16)),
                ("path", models.CharField(db_index=True, max_length=1024)),
                ("query_string", models.TextField(blank=True)),
                ("status_code", models.PositiveSmallIntegerField(default=200)),
                ("response_bytes", models.PositiveIntegerField(default=0)),
                ("content_type", models.CharField(blank=True, max_length=255)),
                ("referrer", models.CharField(blank=True, max_length=1024)),
                ("user_agent", models.TextField(blank=True)),
                ("is_page_view", models.BooleanField(default=False)),
                ("request_headers", models.JSONField(blank=True, default=dict)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="request_events", to="tracker.session")),
                ("visitor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="request_events", to="tracker.visitoridentity")),
            ],
            options={"ordering": ["occurred_at", "id"]},
        ),
        migrations.CreateModel(
            name="ResourceAccessEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(choices=[("browser", "Browser"), ("origin", "Origin"), ("system", "System")], default="browser", max_length=16)),
                ("occurred_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("path", models.CharField(db_index=True, max_length=1024)),
                ("full_url", models.CharField(blank=True, max_length=2048)),
                ("resource_type", models.CharField(choices=[("page", "Page"), ("image", "Image"), ("script", "Script"), ("stylesheet", "Stylesheet"), ("document", "Document"), ("archive", "Archive"), ("media", "Media"), ("other", "Other")], default="other", max_length=32)),
                ("content_type", models.CharField(blank=True, max_length=255)),
                ("bytes_served", models.PositiveIntegerField(default=0)),
                ("action", models.CharField(default="served", max_length=64)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("request_event", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="resource_events", to="tracker.requestevent")),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="resource_events", to="tracker.session")),
            ],
            options={"ordering": ["occurred_at", "id"]},
        ),
        migrations.CreateModel(
            name="DetectionSignal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("signal_type", models.CharField(db_index=True, max_length=128)),
                ("label", models.CharField(max_length=255)),
                ("weight", models.SmallIntegerField(default=0)),
                ("evidence", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="signals", to="tracker.session")),
            ],
            options={"ordering": ["-weight", "id"]},
        ),
    ]
