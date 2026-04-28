import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from payouts.models import Merchant, LedgerEntry

def run():
    print("Seeding database... 🚀")
    
    # We clear previous data to ensure a fresh test environment
    LedgerEntry.objects.all().delete()
    Merchant.objects.all().delete()
    
    print("Cleared existing data.")
    
    # Merchant 1: High Balance
    m1 = Merchant.objects.create(id="f8de1ba2-4bb5-4947-87e9-cd23be40a7c2", name="Acme Corp", balance_paise=15000000) # ₹150,000.00
    LedgerEntry.objects.create(merchant=m1, amount_paise=15000000, entry_type='customer_payment_simulation')
    
    # Merchant 2: Standard Balance (ideal for concurrency test of ₹100 > two ₹60 payouts)
    m2 = Merchant.objects.create(id="9936752a-c907-4451-b115-adfbb13f519c", name="Stark Industries", balance_paise=10000) # ₹100.00
    LedgerEntry.objects.create(merchant=m2, amount_paise=10000, entry_type='customer_payment_simulation')
    
    # Merchant 3: Zero Balance
    m3 = Merchant.objects.create(id="0c730c84-6a53-4cad-9829-931ba03ebdce", name="Wayne Enterprises", balance_paise=0) # ₹0.00
    
    print("\n✅ Successfully seeded 3 Merchants:")
    print(f"1. {m1.name}\n   ID: {m1.id}\n   Balance: ₹{m1.balance_paise / 100:.2f}")
    print("-" * 30)
    print(f"2. {m2.name}\n   ID: {m2.id}\n   Balance: ₹{m2.balance_paise / 100:.2f}")
    print("-" * 30)
    print(f"3. {m3.name}\n   ID: {m3.id}\n   Balance: ₹{m3.balance_paise / 100:.2f}")
    print("-" * 30)

if __name__ == '__main__':
    run()
