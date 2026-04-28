from django.db import transaction
from django.db.models import F, Sum
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status


from .models import Merchant, Payout, IdempotencyKey, LedgerEntry
from .serializers import PayoutRequestSerializer
from .tasks import process_payout

class MerchantDashboardView(APIView):
    def get(self, request, merchant_id, *args, **kwargs):
        try:
            merchant = Merchant.objects.get(id=merchant_id)
        except Merchant.DoesNotExist:
            return Response({"error": "Not found"}, status=404)
        
        payouts = Payout.objects.filter(merchant=merchant).order_by('-created_at')
        held_balance = (
            Payout.objects
            .filter(merchant=merchant, status__in=[Payout.STATUS_PENDING, Payout.STATUS_PROCESSING])
            .aggregate(total=Sum('amount_paise'))['total'] or 0
        )
        ledger = LedgerEntry.objects.filter(merchant=merchant).order_by('-created_at')[:30]
        
        return Response({
            "id": merchant.id,
            "name": merchant.name,
            "balance_paise": merchant.balance_paise,
            "held_balance_paise": held_balance,
            "payouts": [
                {
                    "id": str(p.id),
                    "amount_paise": p.amount_paise,
                    "bank_account_id": p.bank_account_id,
                    "status": p.status,
                    "created_at": p.created_at.isoformat()
                } for p in payouts
            ],
            "ledger": [
                {
                    "id": str(l.id),
                    "amount_paise": l.amount_paise,
                    "entry_type": l.entry_type,
                    "created_at": l.created_at.isoformat()
                } for l in ledger
            ]
        })

class PayoutRequestView(APIView):
    def post(self, request, *args, **kwargs):
        # 1. Idempotency Check
        idempotency_key_value = request.headers.get('Idempotency-Key')
        if not idempotency_key_value:
            return Response(
                {"error": "Idempotency-Key header is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Scope the key to the merchant. Assuming X-Merchant-ID identifies the caller
        raw_merchant_id = request.headers.get('X-Merchant-ID')
        if not raw_merchant_id:
            return Response({"error": "X-Merchant-ID header is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Open the global atomic transaction loop
        with transaction.atomic():
            # 2. Concurrency-safe lookup + insert of Idempotency Key
            # We lock the row immediately if it exists, blocking other threads with the SAME key
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

            if not created:
                if idempotency_key.is_expired():
                    return Response({"error": "Idempotency key expired"}, status=status.HTTP_400_BAD_REQUEST)
                
                # If cached response exists, exactly replay it.
                if idempotency_key.response_status is not None:
                    return Response(idempotency_key.response_body, status=idempotency_key.response_status)
                else:
                    # Race condition hit - another thread created passing key, but response isn't saved yet!
                    # E.g. Request is "in flight". By throwing a 409, we safely reject duplicate click.
                    return Response({"error": "Request already in progress"}, status=status.HTTP_409_CONFLICT)
            
            # The key is fully brand new. Proceed with the logic execution.
            serializer = PayoutRequestSerializer(data=request.data)
            if not serializer.is_valid():
                response_data = serializer.errors
                response_status = status.HTTP_400_BAD_REQUEST
            else:
                amount_paise = serializer.validated_data['amount_paise']
                bank_account_id = serializer.validated_data['bank_account_id']
                
                try:
                    # 3. Check-Then-Deduct with Database level Lock
                    # select_for_update strictly halts ANY concurrent worker reading this merchant balance
                    merchant = Merchant.objects.select_for_update().get(id=raw_merchant_id)
                except (Merchant.DoesNotExist, ValueError):
                    response_data = {"error": "Invalid or missing X-Merchant-ID"}
                    response_status = status.HTTP_400_BAD_REQUEST
                else:
                    if merchant.balance_paise < amount_paise:
                        response_data = {"error": "Insufficient balance"}
                        response_status = status.HTTP_400_BAD_REQUEST
                    else:
                        # Safe to deduct (Strict database-level math logic evaluated entirely in PG)
                        merchant.balance_paise = F('balance_paise') - amount_paise
                        merchant.save(update_fields=['balance_paise', 'updated_at'])
                        merchant.refresh_from_db() # Refresh instance to get accurate exact int for the response

                        payout = Payout.objects.create(
                            merchant=merchant,
                            amount_paise=amount_paise,
                            bank_account_id=bank_account_id,
                            status=Payout.STATUS_PENDING
                        )
                        
                        # Add a negative debit entry to ledger (strictly negative)
                        LedgerEntry.objects.create(
                            merchant=merchant,
                            amount_paise=-amount_paise,
                            entry_type='payout_hold',
                            payout=payout
                        )
                        
                        # Enqueue Huey task efficiently post-commit
                        transaction.on_commit(lambda: process_payout(payout.id))

                        response_data = {
                            "message": "Payout requested successfully",
                            "payout_id": str(payout.id),
                            "status": payout.status,
                            "balance_paise": merchant.balance_paise
                        }
                        response_status = status.HTTP_201_CREATED

            # 4. Save response cleanly before committing the transaction
            idempotency_key.response_status = response_status
            idempotency_key.response_body = response_data
            idempotency_key.save(update_fields=['response_status', 'response_body'])

        return Response(response_data, status=response_status)
