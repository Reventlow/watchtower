"""Name the sites-framework site after Vagt (allauth needs one).

On a fresh database the site does not exist yet when this runs (Django
creates example.com after all migrations, and only when there is none), so
it is created here. Should an example.com placeholder exist already, it is
renamed; a site an admin has edited is left alone.
"""

from django.conf import settings
from django.core.management.color import no_style
from django.db import migrations

DOMAIN, NAME = "vagt.fynbus.net", "Vagt"


def name_site(apps, schema_editor):
    Site = apps.get_model("sites", "Site")
    if not Site.objects.exists():
        Site.objects.create(pk=getattr(settings, "SITE_ID", 1), domain=DOMAIN, name=NAME)
        sql = schema_editor.connection.ops.sequence_reset_sql(no_style(), [Site])
        with schema_editor.connection.cursor() as cursor:
            for statement in sql:
                cursor.execute(statement)
        return
    Site.objects.filter(domain="example.com").update(domain=DOMAIN, name=NAME)


def unname_site(apps, schema_editor):
    Site = apps.get_model("sites", "Site")
    Site.objects.filter(domain=DOMAIN).update(domain="example.com", name="example.com")


class Migration(migrations.Migration):
    dependencies = [("sites", "0002_alter_domain_unique")]
    operations = [migrations.RunPython(name_site, unname_site)]
