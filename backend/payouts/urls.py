from django.urls import path
from .views import PayoutRequestView

urlpatterns = [
    path('payouts', PayoutRequestView.as_view(), name='payout-request'),
]
