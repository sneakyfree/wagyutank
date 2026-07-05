"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, money, PRODUCT_LABEL } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import Checkout from "../../components/Checkout";

export default function Dashboard() {
  const { user, loading, refresh } = useAuth();
  const [listings, setListings] = useState<any[]>([]);
  const [checkout, setCheckout] = useState<{ secret: string | null; label: string } | null>(null);
  const [onboarding, setOnboarding] = useState(false);
  const [toast, setToast] = useState("");

  function load() { api.myListings().then(setListings).catch(() => {}); }
  useEffect(() => { if (user) load(); }, [user]);

  if (loading) return <div className="container section">Loading…</div>;
  if (!user) return <div className="container section">Please <Link href="/login" className="gold">sign in</Link>.</div>;

  const views = listings.reduce((s, l) => s + (l.views || 0), 0);

  async function startOnboarding() {
    setOnboarding(true);
    try {
      const res = await api.onboard();
      await refresh();
      if (res.onboarding_url) window.location.href = res.onboarding_url;
      else { setToast("Seller account ready (dev mode)."); setTimeout(() => setToast(""), 2500); }
    } catch { setToast("Could not start onboarding."); setTimeout(() => setToast(""), 2500); }
    finally { setOnboarding(false); }
  }

  async function featureListing(id: number, days: number) {
    try {
      const res = await api.featureIntent(id, days);
      if (res.dev_mode) { setToast("Featured (dev mode)."); setTimeout(() => setToast(""), 2500); load(); return; }
      setCheckout({ secret: res.client_secret, label: money(res.amount_cents / 100) });
    } catch (e: any) { setToast(e.message); setTimeout(() => setToast(""), 2500); }
  }

  return (
    <div className="container section">
      <div className="row wrap">
        <div>
          <h1 style={{ fontSize: "1.8rem" }}>{user.display_name}</h1>
          {user.handle && <Link href={`/u/${user.handle}`} className="gold">View my storefront →</Link>}
        </div>
        <div className="spacer" />
        <Link href="/sell" className="btn btn-gold">+ New listing</Link>
      </div>

      {!user.is_seller && (
        <div className="card card-pad" style={{ marginTop: 18, borderColor: "var(--gold)" }}>
          <div className="row wrap">
            <div style={{ flex: 1, minWidth: 220 }}>
              <strong className="gold">Set up payouts to get paid</strong>
              <p className="muted" style={{ margin: "4px 0 0", fontSize: "0.9rem" }}>Connect a Stripe account (2 minutes) so buyers can pay you directly.</p>
            </div>
            <button className="btn btn-gold" disabled={onboarding} onClick={startOnboarding}>
              {onboarding ? "Starting…" : "Set up payouts"}
            </button>
          </div>
        </div>
      )}

      <div className="row wrap" style={{ gap: 14, margin: "22px 0" }}>
        <div className="card card-pad" style={{ flex: 1, minWidth: 130 }}><div className="faint">Active listings</div><div className="big-price">{listings.length}</div></div>
        <div className="card card-pad" style={{ flex: 1, minWidth: 130 }}><div className="faint">Total views</div><div className="big-price">{views}</div></div>
        <div className="card card-pad" style={{ flex: 1, minWidth: 130 }}><div className="faint">Seller rating</div><div className="big-price">{user.seller_rating_count ? user.seller_rating.toFixed(1) : "—"}</div></div>
      </div>

      <div className="section-head"><h2>Your listings</h2></div>
      {listings.length ? (
        <div className="stack">
          {listings.map((l) => (
            <div key={l.id} className="card card-pad row wrap" style={{ gap: 12 }}>
              <Link href={`/listing/${l.id}`} style={{ flex: 1, minWidth: 200 }}>
                <div className="row" style={{ gap: 8 }}>
                  <span className="pill pill-dim">{PRODUCT_LABEL[l.product_type]}</span>
                  {l.featured && <span className="pill">★ Featured</span>}
                </div>
                <div style={{ fontWeight: 700, marginTop: 6 }}>{l.title}</div>
                <div className="faint" style={{ fontSize: "0.82rem" }}>{l.views} views · {l.quantity_display}</div>
              </Link>
              <div className="row" style={{ gap: 8 }}>
                {!l.featured && <button className="btn" onClick={() => featureListing(l.id, 7)}>★ Feature — $19/wk</button>}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="adslot">No listings yet. <Link href="/sell" className="gold">Create your first →</Link></div>
      )}

      {checkout && (
        <Checkout clientSecret={checkout.secret} amountLabel={checkout.label}
          onClose={() => setCheckout(null)}
          onSuccess={() => { setCheckout(null); setToast("Listing featured! ★"); load(); setTimeout(() => setToast(""), 3000); }} />
      )}
      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
