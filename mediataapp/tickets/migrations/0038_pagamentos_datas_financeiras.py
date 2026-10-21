from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0037_ticket_empresa_e_assuncao'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pagamentos',
            name='data_pagamento',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='pagamentos',
            name='data_vencimento',
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='pagamentos',
            name='data_pagamento_realizado',
            field=models.DateField(blank=True, null=True),
        ),
    ]
