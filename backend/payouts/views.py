from django.db import transaction
from django.db.models import F
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Merchant, Payout, IdempotencyKey, LedgerEntry
from .serializers import PayoutRequestSerializer
from .tasks import process_payout

class PayoutRequestView(APIView):
    def post(self, request, *args, **kwargs):
        # 1. Idempotency Check
        idempotency_key_header = request.headers.get('Idempotency-Key')
        if not idempotency_key_header:
            return Response(
                {"error": "Idempotency-Key header is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Scope the key to the merchant. Assuming X-Merchant-ID identifies the caller
        merchant_id = request.headers.get('X-Merchant-ID')
        if not merchant_id:
            return Response({"error": "X-Merchant-ID header is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Open the global atomic transaction loop
        with transaction.atomic():
            # 2. Concurrency-safe lookup + insert of Idempotency Key
            # We lock the row immediately if it exists, blocking other threads with the SAME key
            idem_key, created = IdempotencyKey.objects.select_for_update().get_or_create(
                key=idempotency_key_header,
                merchant_id=merchant_id,
                defaults={'request_path': request.path}
            )

            if not created:
                if idem_key.is_expired():
                    return Response({"error": "Idempotency key expired"}, status=status.HTTP_400_BAD_REQUEST)
                
                # If cached response exists, exactly replay it.
                if idem_key.response_status is not None:
                    return Response(idem_key.response_body, status=idem_key.response_status)
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
                    merchant = Merchant.objects.select_for_update().get(id=merchant_id)
                    
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
                        
                        # Enqueue Huey task directly
                        process_payout(payout.id)

                        response_data = {
                            "message": "Payout requested successfully",
                            "payout_id": str(payout.id),
                            "status": payout.status,
                            "balance_paise": merchant.balance_paise
                        }
                        response_status = status.HTTP_201_CREATED

                except Merchant.DoesNotExist:
                    response_data = {"error": "Merchant not found"}
                    response_status = status.HTTP_404_NOT_FOUND

            # 4. Save response cleanly before committing the transaction
            idem_key.response_status = response_status
            idem_key.response_body = response_data
            idem_key.save(update_fields=['response_status', 'response_body'])

        return Response(response_data, status=response_status)
