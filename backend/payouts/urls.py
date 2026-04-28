from django.urls import path
from .views import PayoutRequestView, MerchantDashboardView

urlpatterns = [
    path('payouts', PayoutRequestView.as_view(), name='payout-request'),
    path('merchants/<uuid:merchant_id>/dashboard', MerchantDashboardView.as_view(), name='merchant-dashboard'),
]
