"""Stripe Connect integration (MASTER_PLAN §4, §5).

- Sellers onboard via Stripe Connect Express (payout + KYC in one step).
- Buyers pay the Stripe processing fee, grossed up so WagyuTank never goes negative
  (the "buyer's premium"). Platform commission is `platform_fee_bps` (0 at launch).
- Buy = destination charge to the seller's connected account with an application fee.
"""
from __future__ import annotations

import math

import stripe

from ..config import settings

# Stripe's standard fee, used to gross up the buyer's total.
STRIPE_PCT = 0.029
STRIPE_FIXED_CENTS = 30

if settings.stripe_secret_key:
    stripe.api_key = settings.stripe_secret_key


def stripe_enabled() -> bool:
    return bool(settings.stripe_secret_key)


def compute_amounts(price_cents: int, platform_fee_bps: int | None = None) -> dict:
    """Given the seller's asking price, return what the buyer pays and the application fee.

    Guarantees: seller nets `price_cents`; platform nets `platform_fee` (>= 0) after Stripe
    takes its cut. The buyer covers the processing fee (grossed up).
    """
    bps = settings.platform_fee_bps if platform_fee_bps is None else platform_fee_bps
    platform_fee = round(price_cents * bps / 10000)
    # T - stripe_fee(T) - platform_fee = price_cents, where stripe_fee = PCT*T + FIXED
    total = (price_cents + platform_fee + STRIPE_FIXED_CENTS) / (1 - STRIPE_PCT)
    buyer_total = math.ceil(total)
    application_fee = buyer_total - price_cents   # stays with platform; covers Stripe + platform_fee
    return {
        "seller_price_cents": price_cents,
        "buyer_total_cents": buyer_total,
        "processing_fee_cents": buyer_total - price_cents,
        "application_fee_cents": application_fee,
        "platform_fee_cents": platform_fee,
    }


def create_express_account(email: str, country: str = "US") -> str:
    acct = stripe.Account.create(
        type="express",
        email=email,
        country=country,
        capabilities={"transfers": {"requested": True}, "card_payments": {"requested": True}},
        business_type="individual",
    )
    return acct.id


def create_onboarding_link(account_id: str, return_url: str, refresh_url: str) -> str:
    link = stripe.AccountLink.create(
        account=account_id,
        return_url=return_url,
        refresh_url=refresh_url,
        type="account_onboarding",
    )
    return link.url


def account_charges_enabled(account_id: str) -> bool:
    try:
        acct = stripe.Account.retrieve(account_id)
        return bool(acct.charges_enabled)
    except Exception:
        return False


def create_buy_intent(
    *, price_cents: int, currency: str, seller_account: str, listing_id: int, buyer_id: int
) -> dict:
    """Destination charge: buyer pays, seller's connected account receives, platform keeps the fee."""
    amounts = compute_amounts(price_cents)
    intent = stripe.PaymentIntent.create(
        amount=amounts["buyer_total_cents"],
        currency=currency.lower(),
        application_fee_amount=amounts["application_fee_cents"],
        transfer_data={"destination": seller_account},
        automatic_payment_methods={"enabled": True},
        metadata={"listing_id": str(listing_id), "buyer_id": str(buyer_id), "kind": "purchase"},
    )
    return {"client_secret": intent.client_secret, "payment_intent": intent.id, **amounts}


def create_feature_intent(*, amount_cents: int, listing_id: int, days: int) -> dict:
    """Platform revenue (no destination): a flat-fee 'Feature this listing' purchase."""
    intent = stripe.PaymentIntent.create(
        amount=amount_cents,
        currency="usd",
        automatic_payment_methods={"enabled": True},
        metadata={"listing_id": str(listing_id), "days": str(days), "kind": "feature"},
    )
    return {"client_secret": intent.client_secret, "payment_intent": intent.id, "amount_cents": amount_cents}


def create_ad_intent(*, amount_cents: int, ad_id: int, tier: str) -> dict:
    """Platform revenue: a self-serve advertising purchase (first month)."""
    intent = stripe.PaymentIntent.create(
        amount=amount_cents,
        currency="usd",
        automatic_payment_methods={"enabled": True},
        metadata={"ad_id": str(ad_id), "tier": tier, "kind": "ad"},
    )
    return {"client_secret": intent.client_secret, "payment_intent": intent.id, "amount_cents": amount_cents}
