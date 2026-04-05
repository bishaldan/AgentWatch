from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0001_initial"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="session",
            old_name="tracker_sess_site_id_6dc1e9_idx",
            new_name="tracker_ses_site_id_f2c64e_idx",
        ),
        migrations.RenameIndex(
            model_name="session",
            old_name="tracker_sess_site_id_1a2fd2_idx",
            new_name="tracker_ses_site_id_c8a474_idx",
        ),
    ]
