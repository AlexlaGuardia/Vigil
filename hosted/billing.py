"""Stripe billing — checkout, portal, webhooks."""

import stripe
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse

from hosted.auth import read_session_cookie, SESSION_COOKIE
from hosted.config import STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICES, APP_URL

router = APIRouter(prefix="/billing")

stripe.api_key = STRIPE_SECRET_KEY


def _get_user_or_redirect(request: Request):
    """Get current user from session or None."""
    from hosted.app import get_platform_db
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None, None
    account_id = read_session_cookie(cookie)
    if not account_id:
        return None, None
    pdb = get_platform_db()
    return pdb.get_account(account_id), pdb


@router.post("/checkout/{tier}")
async def create_checkout(tier: str, request: Request):
    """Create a Stripe Checkout session for upgrading."""
    user, pdb = _get_user_or_redirect(request)
    if not user:
        raise HTTPException(401, "Not authenticated")

    price_id = STRIPE_PRICES.get(tier)
    if not price_id:
        raise HTTPException(400, f"Invalid tier: {tier}. Valid: {list(STRIPE_PRICES.keys())}")

    # Get or create Stripe customer
    customer_id = user.get("stripe_customer_id")
    if not customer_id:
        customer = stripe.Customer.create(
            email=user["email"],
            name=user["name"],
            metadata={"vigil_account_id": user["id"]},
        )
        customer_id = customer.id
        pdb.update_tier(user["id"], user["tier"], stripe_customer_id=customer_id)

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{APP_URL}/dashboard?upgraded=true",
        cancel_url=f"{APP_URL}/dashboard",
        metadata={"vigil_account_id": user["id"], "tier": tier},
    )

    return RedirectResponse(session.url, status_code=303)


@router.post("/portal")
async def create_portal(request: Request):
    """Create a Stripe Customer Portal session for managing subscription."""
    user, pdb = _get_user_or_redirect(request)
    if not user:
        raise HTTPException(401, "Not authenticated")

    customer_id = user.get("stripe_customer_id")
    if not customer_id:
        raise HTTPException(400, "No active subscription")

    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{APP_URL}/dashboard",
    )

    return RedirectResponse(session.url, status_code=303)


@router.post("/webhook")
async def webhook(request: Request):
    """Handle Stripe webhook events."""
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(400, "Invalid webhook signature")

    from hosted.app import get_platform_db
    pdb = get_platform_db()

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        account_id = session["metadata"].get("vigil_account_id")
        tier = session["metadata"].get("tier")
        customer_id = session.get("customer")
        if account_id and tier:
            pdb.update_tier(account_id, tier, stripe_customer_id=customer_id)

    elif event["type"] == "customer.subscription.updated":
        sub = event["data"]["object"]
        customer_id = sub["customer"]
        # Find account by stripe customer ID
        account = _find_account_by_customer(pdb, customer_id)
        if account:
            # Determine tier from price
            price_id = sub["items"]["data"][0]["price"]["id"] if sub["items"]["data"] else None
            tier = _price_to_tier(price_id)
            if tier:
                pdb.update_tier(account["id"], tier)

    elif event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        customer_id = sub["customer"]
        account = _find_account_by_customer(pdb, customer_id)
        if account:
            pdb.update_tier(account["id"], "free")

    elif event["type"] == "invoice.payment_failed":
        # Could send an email notification — for now just log
        pass

    return JSONResponse({"received": True})


def _find_account_by_customer(pdb, customer_id: str):
    """Find account by Stripe customer ID."""
    with pdb.connect() as conn:
        row = conn.execute(
            "SELECT * FROM accounts WHERE stripe_customer_id = ?", (customer_id,)
        ).fetchone()
        return dict(row) if row else None


def _price_to_tier(price_id: str) -> str | None:
    """Map a Stripe price ID back to a tier name."""
    for tier, pid in STRIPE_PRICES.items():
        if pid == price_id:
            return tier
    return None
