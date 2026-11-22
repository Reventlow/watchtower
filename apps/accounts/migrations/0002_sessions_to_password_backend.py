"""Keep existing logins across the switch to Vagt's own backends.

A session remembers the backend that logged its user in, and Django drops
the session when that backend is no longer in AUTHENTICATION_BACKENDS.
Before Microsoft sign-in, every login went through Django's ModelBackend;
now passwords go through ``apps.accounts.backends.PasswordBackend`` (the
same check, plus the VAGT_SSO_ONLY rule). Without this migration, the
deploy would log everyone out, wall displays included.

Sessions that cannot be decoded (e.g. made with another SECRET_KEY) are
left alone; Django ignores them anyway.
"""

from django.db import migrations

OLD = "django.contrib.auth.backends.ModelBackend"
NEW = "apps.accounts.backends.PasswordBackend"
BACKEND_KEY = "_auth_user_backend"


def _move(apps, schema_editor, old, new):
    from django.contrib.sessions.backends.db import SessionStore

    Session = apps.get_model("sessions", "Session")
    store = SessionStore()
    for session in Session.objects.all().iterator():
        try:
            data = store.decode(session.session_data)
        except Exception:  # undecodable: Django treats it as empty anyway
            continue
        if data.get(BACKEND_KEY) == old:
            data[BACKEND_KEY] = new
            session.session_data = store.encode(data)
            session.save(update_fields=["session_data"])


def forwards(apps, schema_editor):
    _move(apps, schema_editor, OLD, NEW)


def backwards(apps, schema_editor):
    _move(apps, schema_editor, NEW, OLD)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_site_domain"),
        ("sessions", "0001_initial"),
    ]
    operations = [migrations.RunPython(forwards, backwards)]
