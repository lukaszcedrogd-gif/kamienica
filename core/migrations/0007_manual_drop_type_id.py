# Generated manually to fix a schema issue

from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_financialtransaction_contractor_and_more'),
    ]

    operations = [
        # This migration attempts to manually drop the 'type_id' column
        # that should have been removed by migration 0005 but appears to
        # still exist in the database schema, causing IntegrityError.
        # We use 'DROP COLUMN IF EXISTS' to avoid errors if the column
        # has somehow been removed in the meantime.
        migrations.RunSQL(
            sql="ALTER TABLE core_financialtransaction DROP COLUMN type_id;",
            reverse_sql=migrations.RunSQL.noop, # We don't want to recreate the column
        )
    ]
