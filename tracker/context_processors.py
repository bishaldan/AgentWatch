from django.conf import settings


def product_context(_: object) -> dict[str, str]:
    return {
        "product_name": "AI Agent Traffic Intelligence",
        "tracker_site_id": settings.TRACKER_SITE_ID,
    }
