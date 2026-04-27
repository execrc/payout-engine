import uuid
from django.db import models
from django.utils import timezone

class Merchant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    balance_paise = models.BigIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.balance_paise} paise"

class Payout(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, related_name='payouts', on_delete=models.PROTECT)
    amount_paise = models.BigIntegerField()
    bank_account_id = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payout {self.id} for {self.merchant.name} - {self.status}"

class LedgerEntry(models.Model):
    """
    By maintaining this ledger table, we can easily enforce their invariant: 
    "The sum of credits minus debits must always equal the displayed balance"
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, related_name='ledger_entries', on_delete=models.PROTECT)
    amount_paise = models.BigIntegerField()
    entry_type = models.CharField(max_length=50) # Examples: 'customer_payment', 'payout_hold', 'payout_refund'
    
    payout = models.ForeignKey(Payout, on_delete=models.SET_NULL, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Ledger {self.id} | {self.merchant.name} | {self.amount_paise}"


class IdempotencyKey(models.Model):
    """
    Guarantees API operations don't duplicate state on network retry.
    """
    key = models.UUIDField()
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE)
    
    request_path = models.CharField(max_length=255)
    response_status = models.IntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Prompt: "Keys scoped per merchant"
        unique_together = ('key', 'merchant')

    def is_expired(self):
        # Prompt: "Keys expire after 24 hours"
        return timezone.now() > self.created_at + timezone.timedelta(hours=24)
