from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0026_add_verified_to_financialtransaction'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='is_admin',
            field=models.BooleanField(default=False, verbose_name='Administrator systemu'),
        ),
        migrations.AddField(
            model_name='historicaluser',
            name='is_admin',
            field=models.BooleanField(default=False, verbose_name='Administrator systemu'),
        ),
    ]
