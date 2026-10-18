import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_no_missing_migrations(settings):
    # pretix's test settings disable migrations outside of GitHub Actions.
    settings.MIGRATION_MODULES = {}
    # Exits with a non-zero code if the models have changes without a migration.
    call_command("makemigrations", "pretix_roomsharing", check=True, dry_run=True)
