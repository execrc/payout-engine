import time
import random
from huey.contrib.djhuey import db_task
from django.db import transaction
from django.db.models import F
from .models import Payout, Merchant, LedgerEntry

def call_bank_simulation():
    """
    Simulates external bank API behavior cleanly:
    - 70% success
    - 20% fail
    - 10% hang
    """
    roll = random.randint(1, 100)
    
    if roll <= 10:
        time.sleep(31) # Simulates hanging
        raise TimeoutError("Bank API Hung for >30s")
    elif roll <= 30: # 11-30
        return False # Failed
    else: # 31-100
        return True # Success

@db_task()
def process_payout(payout_id, attempt=1):
    # Maximum 3 attempts
    MAX_ATTEMPTS = 3
    
    # Fast transition using atomic lock
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(id=payout_id)
        
        # IMPORTANT STATE MACHINE CONSTRAINT 
        # Legal: pending -> processing
        # Illegal: completed -> processing, failed -> processing
        if payout.status not in [Payout.STATUS_PENDING, Payout.STATUS_PROCESSING]:
            raise ValueError(f"Illegal state transition attempted. Status is currently: {payout.status}")
        
        payout.status = Payout.STATUS_PROCESSING
        payout.save(update_fields=['status', 'updated_at'])

    try:
        success = call_bank_simulation()
    except TimeoutError:
        if attempt < MAX_ATTEMPTS:
            # Exponential Backoff Retry (e.g. 2s -> 4s)
            delay_seconds = 2 ** attempt
            process_payout.schedule(args=(payout_id, attempt + 1), delay=delay_seconds)
            return
        else:
            # Max retries exhausted, we must cleanly execute the atomic fail/refund operation
            success = False
            
    # Resolve Final Status
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(id=payout_id)
        
        if payout.status != Payout.STATUS_PROCESSING:
            # Block illegal reverse flows like failed -> completed
            raise ValueError(f"Cannot resolve payout. Expected processing, got {payout.status}")
            
        if success:
            payout.status = Payout.STATUS_COMPLETED
            payout.save(update_fields=['status', 'updated_at'])
            # Payout fully complete. Balance already deducted from merchant initially.
        else:
            payout.status = Payout.STATUS_FAILED
            payout.save(update_fields=['status', 'updated_at'])
            
            # Atomic Refund to Merchant
            merchant = Merchant.objects.select_for_update().get(id=payout.merchant_id)
            merchant.balance_paise = F('balance_paise') + payout.amount_paise
            merchant.save(update_fields=['balance_paise', 'updated_at'])
            
            # Log exact atomic trace of the refund
            LedgerEntry.objects.create(
                merchant=merchant,
                amount_paise=payout.amount_paise,
                entry_type='payout_refund',
                payout=payout
            )
