from django.db import models

class Transaction(models.Model):
    TRANSACTION_TYPE_CHOICES = (
        ('income', 'Wpływy'),
        ('expense', 'Wydatki'),
    )

    date = models.DateField()
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=7, choices=TRANSACTION_TYPE_CHOICES)

    def __str__(self):
        return f"{self.date} - {self.description} - {self.amount}"