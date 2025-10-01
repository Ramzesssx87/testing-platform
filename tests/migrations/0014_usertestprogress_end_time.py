# Создайте файл миграции (например: 0013_usertestprogress_end_time.py)
from django.db import migrations, models
import django.utils.timezone

class Migration(migrations.Migration):

    dependencies = [
        ('tests', '0012_quizsession_quizparticipant'),
    ]

    operations = [
        migrations.AddField(
            model_name='usertestprogress',
            name='end_time',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Время окончания теста'),
        ),
    ]