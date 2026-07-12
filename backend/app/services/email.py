"""Transactional + marketing email via Resend (wagyutank.com is a verified sender).

Falls back to logging when no key is configured, so dev/test never crashes and
password-reset flows can still surface a token for testing."""
import logging

import httpx

from ..config import settings
from .. import tank

log = logging.getLogger("wagyutank.email")


def _mail_from() -> str:
    """The From address. An explicit MAIL_FROM env wins (e.g. a tank whose own
    domain isn't a verified Resend sender yet); otherwise derive it from the tank's
    brand as "Name <office@its-domain>", so every clone sends from its own real,
    replyable address instead of a noreply@. Never returns a noreply@ default."""
    override = (settings.mail_from or "").strip()
    if override:
        return override
    try:
        b = tank.brand()
        addr = (b.get("contactEmail") or "").strip()
        name = (b.get("name") or "").strip()
        if addr:
            return f"{name} <{addr}>" if name else addr
    except Exception:
        pass
    return "WagyuTank <office@wagyutank.com>"


def _api_key() -> str:
    try:
        from . import settings_store
        return settings_store.get("resend_api_key", None) or settings.resend_api_key
    except Exception:
        return settings.resend_api_key


def enabled() -> bool:
    return bool(_api_key())


def send(to: str, subject: str, html: str, *, text: str | None = None,
         reply_to: str | None = None) -> bool:
    """Send one email. Returns True on success; logs and returns False otherwise."""
    key = _api_key()
    if not key:
        log.warning("EMAIL (no key — not sent) to=%s subject=%s", to, subject)
        return False
    payload = {"from": _mail_from(), "to": [to], "subject": subject, "html": html}
    if text:
        payload["text"] = text
    if reply_to:
        payload["reply_to"] = reply_to
    try:
        r = httpx.post("https://api.resend.com/emails",
                       headers={"Authorization": f"Bearer {key}"}, json=payload, timeout=20)
        if r.status_code < 300:
            return True
        log.error("Resend error %s: %s", r.status_code, r.text[:200])
    except Exception as e:
        log.error("Resend send failed: %s", e)
    return False


def _brand_bits() -> tuple[str, str, str, str]:
    """(name, gold, footerBlurb, breed) from the tank's brand — so every clone's
    emails carry its own name/colors/breed instead of hardcoded WagyuTank."""
    try:
        b = tank.brand()
        name = (b.get("name") or "WagyuTank").strip()
        gold = ((b.get("colors") or {}).get("gold") or "#8a6d2b").strip()
        footer = (b.get("footerBlurb") or b.get("tagline") or "the world's genetics marketplace").strip()
        breed = (b.get("breed") or "livestock").strip()
        return name, gold, footer, breed
    except Exception:
        return "WagyuTank", "#8a6d2b", "the world's marketplace for frozen Wagyu genetics", "Wagyu"


def _shell(body_html: str) -> str:
    name, gold, footer, _ = _brand_bits()
    return f"""<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:520px;margin:0 auto;color:#1a1a1a">
      <div style="font-size:1.4rem;font-weight:800;color:{gold};padding:8px 0">{name}</div>
      <div style="border-top:2px solid {gold};padding-top:16px;font-size:15px;line-height:1.6">{body_html}</div>
      <p style="color:#999;font-size:12px;margin-top:28px">{name} — {footer}.<br>
      If you didn't expect this email, you can ignore it.</p></div>"""


def send_password_reset(to: str, reset_url: str) -> bool:
    name, gold, _, _ = _brand_bits()
    html = _shell(
        f"<p>We received a request to reset your {name} password.</p>"
        f"<p><a href='{reset_url}' style='background:{gold};color:#1a1a1a;padding:11px 20px;"
        f"border-radius:8px;text-decoration:none;font-weight:700;display:inline-block'>Reset my password</a></p>"
        f"<p style='color:#666;font-size:13px'>This link expires in 45 minutes and can be used once. "
        f"If you didn't ask to reset your password, nothing has changed.</p>")
    return send(to, f"Reset your {name} password", html,
                text=f"Reset your {name} password: {reset_url} (expires in 45 minutes)")


def send_bulk(messages: list[dict]) -> int:
    """Send a batch of emails via Resend's batch API (chunks of 100). Each message:
    {to, subject, html, unsubscribe_url}. Returns the count accepted."""
    key = _api_key()
    if not key:
        for m in messages:
            log.warning("EMAIL BULK (no key — not sent) to=%s", m.get("to"))
        return 0
    sent = 0
    for i in range(0, len(messages), 100):
        chunk = messages[i:i + 100]
        payload = []
        for m in chunk:
            obj = {"from": _mail_from(), "to": [m["to"]], "subject": m["subject"],
                   "html": m["html"]}
            if m.get("unsubscribe_url"):
                obj["headers"] = {"List-Unsubscribe": f"<{m['unsubscribe_url']}>",
                                  "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
            payload.append(obj)
        try:
            r = httpx.post("https://api.resend.com/emails/batch",
                           headers={"Authorization": f"Bearer {key}"}, json=payload, timeout=30)
            if r.status_code < 300:
                sent += len(chunk)
            else:
                log.error("Resend batch error %s: %s", r.status_code, r.text[:200])
        except Exception as e:
            log.error("Resend batch failed: %s", e)
    return sent


def campaign_html(body_html: str, unsubscribe_url: str) -> str:
    return _shell(body_html) + (
        f"<div style='text-align:center;color:#aaa;font-size:11px;margin-top:8px'>"
        f"<a href='{unsubscribe_url}' style='color:#aaa'>Unsubscribe</a> from marketing emails.</div>")


def send_welcome(to: str, name: str) -> bool:
    brand_name, gold, _, breed = _brand_bits()
    html = _shell(
        f"<p>Welcome to {brand_name}, {name}!</p>"
        f"<p>You can list genetics in under a minute, browse offerings from around the world, "
        f"and dig into the deepest {breed} breed history anywhere.</p>"
        f"<p><a href='{settings.app_base_url}/sell' style='color:{gold};font-weight:700'>List your first genetics →</a></p>")
    return send(to, f"Welcome to {brand_name}", html)
