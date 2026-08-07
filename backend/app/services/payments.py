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


#: Stripe renders a card statement as "<account prefix>* <suffix>" and caps the
#: WHOLE string at 22 characters. The live account's prefix is "WINDYPRO" (it is
#: shared with Windy Word billing), which spends 10 of those on "WINDYPRO* " and
#: leaves 12. So a tank's suffix must fit in 12 or Stripe rejects the charge.
_DESCRIPTOR_MAX = 12


def _tank_ident() -> tuple[str, str, str]:
    """(platform_key, brand_name, statement_suffix) for the tank serving this request.

    One Stripe account bills every tank, so without this a WagyuTank ad and a
    GirTank ad are indistinguishable — the buyer's statement would read only
    "WINDYPRO", and the dashboard would show five brands as one undifferentiated
    pile. `brand.statementDescriptor` in tank.json wins when a derived name would
    be truncated into nonsense (MurrayGreyTank -> "MURRAYGREYTA")."""
    from .. import tank
    try:
        key = tank.key() or "wagyu"
        b = tank.brand() or {}
        name = (b.get("name") or "WagyuTank").strip()
        explicit = (b.get("statementDescriptor") or "").strip()
    except Exception:
        return "wagyu", "WagyuTank", "WAGYUTANK"
    raw = explicit or name
    # Stripe forbids < > \ ' " * in descriptors; keep it to plain A-Z0-9.
    suffix = "".join(ch for ch in raw.upper() if ch.isalnum())[:_DESCRIPTOR_MAX]
    return key, name, (suffix or "WAGYUTANK")


def _charge_context(**extra) -> dict:
    """Metadata + statement descriptor every charge should carry."""
    key, name, suffix = _tank_ident()
    meta = {"platform": key, "brand": name}
    meta.update({k: v for k, v in extra.items() if v is not None})
    return {"metadata": meta, "statement_descriptor_suffix": suffix}


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
        **_charge_context(listing_id=str(listing_id), buyer_id=str(buyer_id), kind="purchase"),
    )
    return {"client_secret": intent.client_secret, "payment_intent": intent.id, **amounts}


def create_feature_intent(*, amount_cents: int, listing_id: int, days: int) -> dict:
    """Platform revenue (no destination): a flat-fee 'Feature this listing' purchase."""
    intent = stripe.PaymentIntent.create(
        amount=amount_cents,
        currency="usd",
        automatic_payment_methods={"enabled": True},
        **_charge_context(listing_id=str(listing_id), days=str(days), kind="feature"),
    )
    return {"client_secret": intent.client_secret, "payment_intent": intent.id, "amount_cents": amount_cents}


def create_ad_intent(*, amount_cents: int, ad_id: int, tier: str) -> dict:
    """Platform revenue: a self-serve advertising purchase (first month)."""
    intent = stripe.PaymentIntent.create(
        amount=amount_cents,
        currency="usd",
        automatic_payment_methods={"enabled": True},
        **_charge_context(ad_id=str(ad_id), tier=tier, kind="ad"),
    )
    return {"client_secret": intent.client_secret, "payment_intent": intent.id, "amount_cents": amount_cents}
