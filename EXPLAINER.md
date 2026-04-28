# EXPLAINER.md

## 1. The Ledger

**Balance calculation:**

Balance is stored as a cached `balance_paise` (BigIntegerField) directly on the `Merchant` row. It is read as:

```python
merchant.balance_paise
```

It is never derived by summing the ledger on read. That would be O(n) per request and unscalable. Instead, the cached column is updated atomically via Django's `F()` expressions on every debit/credit, so Postgres executes the math, not Python.

The `LedgerEntry` table is append-only and exists purely for auditability and invariant verification:

```python
credit_sum = self.ledger.filter(amount_paise__gt=0).aggregate(Sum('amount_paise'))['amount_paise__sum'] or 0
debit_sum = self.ledger.filter(amount_paise__lt=0).aggregate(Sum('amount_paise'))['amount_paise__sum'] or 0
assert self.balance_paise == (credit_sum + debit_sum)
```

Credits are stored as positive integers. Debits (payout holds, payout refunds) are stored as negative integers. The invariant always holds: `balance_paise == sum of all ledger entries`.

---

## 2. The Lock

**Exact code:**

```python
with transaction.atomic():
    merchant = Merchant.objects.select_for_update().get(id=merchant_id)

    if merchant.balance_paise < amount_paise:
        response_data = {"error": "Insufficient balance"}
        response_status = status.HTTP_400_BAD_REQUEST
    else:
        merchant.balance_paise = F('balance_paise') - amount_paise
        merchant.save(update_fields=['balance_paise', 'updated_at'])
```

**Database primitive:** Postgres row-level locking via `SELECT FOR UPDATE`.

When Request A hits `select_for_update().get(id=merchant_id)`, Postgres acquires an exclusive lock on that merchant row. Request B arriving simultaneously for the same merchant blocks entirely at the `SELECT FOR UPDATE` — it cannot read the row until A's transaction commits. Once A commits with the deducted balance, B wakes up, reads the updated balance, and fails the `balance < amount` check cleanly.

This eliminates the classic check-then-deduct race where two threads both read the same stale balance and both pass the check.

---

## 3. The Idempotency

**How the system knows it has seen a key before:**

A dedicated `IdempotencyKey` table has a unique constraint on `(merchant_id, key)`. On every payout request, inside a single `transaction.atomic()` block:

```python
try:
    idempotency_key = IdempotencyKey.objects.select_for_update().get(
        key=idempotency_key_value,
        merchant_id=raw_merchant_id
    )
    created = False
except IdempotencyKey.DoesNotExist:
    idempotency_key = IdempotencyKey.objects.create(
        key=idempotency_key_value,
        merchant_id=raw_merchant_id,
        request_path=request.path
    )
    created = True
```

If `created` is `False`, the key was seen before. The cached `response_body` and `response_status` are replayed exactly.

**What happens if the first request is still in flight when the second arrives:**

The first request creates the `IdempotencyKey` row but hasn't saved the response yet (`response_status` is null). The second request's `get()` finds the rigidly locked existing row (created=False) and gracefully kicks back:

```python
if idempotency_key.response_status is not None:
    return Response(idempotency_key.response_body, status=idempotency_key.response_status)
else:
    return Response({"error": "Request already in progress"}, status=status.HTTP_409_CONFLICT)
```

It returns 409 immediately rather than proceeding to touch the ledger. The `select_for_update()` on the idempotency row also means if two requests race on key creation itself, the unique constraint on `(merchant_id, key)` acts as the final backstop — one insert wins, the other gets an integrity error.

Keys expire after 24 hours via the `is_expired()` check.

---

## 4. The State Machine

**Legal transitions:** `pending → processing → completed` or `pending → processing → failed`

**Where illegal transitions are blocked:**

In `tasks.py`, before every state change, the payout is fetched under `select_for_update()` and the current status is asserted:

```python
# Transition to processing
with transaction.atomic():
    payout = Payout.objects.select_for_update().get(id=payout_id)

    if payout.status not in [Payout.STATUS_PENDING, Payout.STATUS_PROCESSING]:
        raise ValueError(f"Illegal state transition attempted. Status is currently: {payout.status}")

    payout.status = Payout.STATUS_PROCESSING
    payout.save(update_fields=['status', 'updated_at'])

# Resolve final status
with transaction.atomic():
    payout = Payout.objects.select_for_update().get(id=payout_id)

    if payout.status != Payout.STATUS_PROCESSING:
        raise ValueError(f"Cannot resolve payout. Expected processing, got {payout.status}")
```

The second guard is what blocks `failed → completed`. If a stale retry hook picks up an already-failed payout, it locks the row, sees it is not `processing`, and raises before touching the ledger or merchant balance.

The refund on failure is atomic with the state transition — both happen inside the same `transaction.atomic()` block, so there is no window where a payout is marked failed but the balance hasn't been returned.

---

## 5. Standard ORM Pitfalls

**Common naive Django ORM approach:**

```python
held_balance = sum(p.amount_paise for p in payouts if p.status in [Payout.STATUS_PENDING, Payout.STATUS_PROCESSING])
```

**Why this is dangerous:**

This statically fetches absolutely all payout rows into Python and sums them in local application memory. Advanced financial backend architectures practically outright ban balance calculations executing outside database-level operations to avoid hitting race conditions via Python arithmetic bounding on fetched rows. Additionally, on a merchant with thousands of payouts, this acts as a massive linear N-row fetch purely for a single aggregated integer, instantly violating the horizontal scaling capabilities of the immutable ledger structure.

**The robust PostgreSQL native solution:**

```python
from django.db.models import Sum

held_balance = (
    Payout.objects
    .filter(merchant=merchant, status__in=[Payout.STATUS_PENDING, Payout.STATUS_PROCESSING])
    .aggregate(total=Sum('amount_paise'))['total'] or 0
)
```

This executes a single `SELECT SUM(amount_paise) WHERE ...` in Postgres and returns one integer. No rows are hydrated into Python objects.