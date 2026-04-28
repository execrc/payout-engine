import threading
from django.test import TransactionTestCase
from rest_framework.test import APIClient
from django.db import connection
from payouts.models import Merchant, Payout
import uuid
import threading

class ConcurrencyAndIdempotencyTest(TransactionTestCase):
    def setUp(self):
        self.merchant = Merchant.objects.create(name="Test Merchant", balance_paise=10000) # Exactly 100 rupees (10000 paise)

    def test_check_then_deduct_race_condition(self):
        """
        A merchant with 100 rupees balance submits two simultaneous 60 rupee 
        payout requests. Exactly one should succeed. The other must be rejected cleanly.
        """
        results = []
        barrier = threading.Barrier(2)

        def make_request(idem_key):
            barrier.wait() # Forces absolute thread synchronization for the ultimate race condition test
            client = APIClient()
            response = client.post(
                '/api/v1/payouts',
                {"amount_paise": 6000, "bank_account_id": "bank_x"},
                format='json',
                HTTP_IDEMPOTENCY_KEY=idem_key,
                HTTP_X_MERCHANT_ID=str(self.merchant.id)
            )
            results.append(response.status_code)
            connection.close()

        # Fire threads simultaneously
        t1 = threading.Thread(target=make_request, args=(str(uuid.uuid4()),))
        t2 = threading.Thread(target=make_request, args=(str(uuid.uuid4()),))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # One must succeed, one must fail strictly!
        self.assertIn(201, results)
        self.assertIn(400, results)
        
        # Balance must be strictly 40 rupees (4000 paise) (10000 - 6000)
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.balance_paise, 4000)
        
        # Payout created count must be strictly 1
        self.assertEqual(Payout.objects.count(), 1)


    def test_idempotency_duplicate_calls(self):
        """
        Idempotency test. Second call with the same key returns the exact same response 
        as the first. No duplicate payout created.
        """
        client = APIClient()
        idem_key = str(uuid.uuid4())
        
        # First request
        res1 = client.post(
            '/api/v1/payouts',
            {"amount_paise": 2000, "bank_account_id": "bank_y"},
            format='json',
            HTTP_IDEMPOTENCY_KEY=idem_key,
            HTTP_X_MERCHANT_ID=str(self.merchant.id)
        )
        self.assertEqual(res1.status_code, 201)
        
        # Second exact duplicate request
        res2 = client.post(
            '/api/v1/payouts',
            {"amount_paise": 2000, "bank_account_id": "bank_y"},
            format='json',
            HTTP_IDEMPOTENCY_KEY=idem_key,
            HTTP_X_MERCHANT_ID=str(self.merchant.id)
        )
        self.assertEqual(res2.status_code, 201)
        
        # Assert exact JSON response body
        self.assertEqual(res1.json(), res2.json())
        
        # Assert database integrity exactly
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.balance_paise, 8000) # Only 2000 deducted once
        self.assertEqual(Payout.objects.count(), 1) # Only one payout physically created
