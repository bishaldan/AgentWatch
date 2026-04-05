from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create or update the initial admin user from environment variables."

    def handle(self, *args, **options):
        email = settings.TRACKER_BOOTSTRAP_ADMIN_EMAIL
        password = settings.TRACKER_BOOTSTRAP_ADMIN_PASSWORD

        if not email or not password:
            self.stdout.write("TRACKER_BOOTSTRAP_ADMIN_EMAIL / TRACKER_BOOTSTRAP_ADMIN_PASSWORD not set; skipping bootstrap.")
            return

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=email,
            defaults={
                "email": email,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()

        verb = "Created" if created else "Updated"
        self.stdout.write(f"{verb} admin user {email}.")
