"""
Stripe integration. All keys come from environment variables -- nothing
here works without STRIPE_SECRET_KEY set, and it fails loudly (not
silently) if you try to use it unconfigured, so a missing key can't be
mistaken for "it's free."

Card data never touches this app: checkout happens on Stripe's own hosted
page (PCI compliance is Stripe's problem, not ours), and subscription
management happens through Stripe's hosted Customer Portal.
"""
import os
import stripe

STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')
STRIPE_PRICE_ID = os.environ.get('STRIPE_PRICE_ID')  # the $4.99/mo recurring Price in your Stripe dashboard
PUBLIC_BASE_URL = os.environ.get('PUBLIC_BASE_URL', 'http://localhost:8000')

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


def billing_configured():
    return bool(STRIPE_SECRET_KEY and STRIPE_PRICE_ID)


def create_checkout_session(user_email, user_id, stripe_customer_id=None):
    if not billing_configured():
        raise RuntimeError("Stripe is not configured (missing STRIPE_SECRET_KEY / STRIPE_PRICE_ID).")
    kwargs = dict(
        mode='subscription',
        line_items=[{'price': STRIPE_PRICE_ID, 'quantity': 1}],
        success_url=f"{PUBLIC_BASE_URL}/dashboard?checkout=success",
        cancel_url=f"{PUBLIC_BASE_URL}/pricing?checkout=cancelled",
        client_reference_id=str(user_id),
    )
    if stripe_customer_id:
        kwargs['customer'] = stripe_customer_id
    else:
        kwargs['customer_email'] = user_email
    session = stripe.checkout.Session.create(**kwargs)
    return session.url


def create_portal_session(stripe_customer_id):
    if not billing_configured():
        raise RuntimeError("Stripe is not configured.")
    session = stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url=f"{PUBLIC_BASE_URL}/dashboard",
    )
    return session.url


def verify_webhook(payload, sig_header):
    if not STRIPE_WEBHOOK_SECRET:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET is not set -- refusing to process unverified webhooks.")
    return stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
