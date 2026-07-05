"use client";
import { useEffect, useMemo, useState } from "react";
import { loadStripe, Stripe } from "@stripe/stripe-js";
import { Elements, PaymentElement, useStripe, useElements } from "@stripe/react-stripe-js";
import { api, money } from "../lib/api";

let _stripePromise: Promise<Stripe | null> | null = null;
function stripePromise(pk: string) {
  if (!_stripePromise) _stripePromise = loadStripe(pk);
  return _stripePromise;
}

function PayForm({ label, onDone }: { label: string; onDone: (ok: boolean) => void }) {
  const stripe = useStripe();
  const elements = useElements();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!stripe || !elements) return;
    setBusy(true); setErr("");
    const { error, paymentIntent } = await stripe.confirmPayment({ elements, redirect: "if_required" });
    if (error) { setErr(error.message || "Payment failed"); setBusy(false); }
    else if (paymentIntent && paymentIntent.status === "succeeded") { onDone(true); }
    else { setErr("Payment did not complete."); setBusy(false); }
  }

  return (
    <form onSubmit={submit} className="stack">
      <PaymentElement />
      <p className="help">Test mode — use card 4242 4242 4242 4242, any future date, any CVC.</p>
      {err && <p className="help" style={{ color: "var(--red)" }}>{err}</p>}
      <button className="btn btn-gold btn-block btn-lg" disabled={!stripe || busy}>
        {busy ? "Processing…" : `Pay ${label}`}
      </button>
    </form>
  );
}

export default function Checkout({
  clientSecret, amountLabel, onClose, onSuccess,
}: {
  clientSecret: string | null; amountLabel: string; onClose: () => void; onSuccess: () => void;
}) {
  const [pk, setPk] = useState<string | null>(null);
  useEffect(() => { api.paymentsConfig().then((c) => setPk(c.publishable_key)).catch(() => {}); }, []);

  const options = useMemo(
    () => (clientSecret ? { clientSecret, appearance: { theme: "night" as const, variables: { colorPrimary: "#d9a441" } } } : undefined),
    [clientSecret]
  );

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "grid", placeItems: "center", zIndex: 200, padding: 16 }} onClick={onClose}>
      <div className="card card-pad" style={{ maxWidth: 460, width: "100%" }} onClick={(e) => e.stopPropagation()}>
        <div className="row"><h2 style={{ fontSize: "1.3rem", margin: 0 }}>Checkout</h2><div className="spacer" /><button className="btn btn-ghost" onClick={onClose}>✕</button></div>
        <div className="big-price" style={{ margin: "10px 0 16px" }}>{amountLabel}</div>
        {!clientSecret ? (
          <p className="muted">Preparing payment…</p>
        ) : !pk ? (
          <p className="muted">Loading Stripe…</p>
        ) : (
          <Elements stripe={stripePromise(pk)} options={options}>
            <PayForm label={amountLabel} onDone={(ok) => (ok ? onSuccess() : onClose())} />
          </Elements>
        )}
      </div>
    </div>
  );
}
