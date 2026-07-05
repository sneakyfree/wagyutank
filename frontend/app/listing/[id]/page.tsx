"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, PRODUCT_GLYPH, PRODUCT_LABEL, money } from "../../../lib/api";
import { useAuth } from "../../../lib/auth";
import Checkout from "../../../components/Checkout";

export default function ListingDetail() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const [l, setL] = useState<any>(null);
  const [bid, setBid] = useState("");
  const [toast, setToast] = useState("");
  const [err, setErr] = useState("");
  const [checkout, setCheckout] = useState<{ secret: string | null; label: string } | null>(null);

  function load() { api.listing(id).then(setL).catch(() => setL(false as any)); }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  if (l === false) return <div className="container section">Listing not found.</div>;
  if (!l) return <div className="container section">Loading…</div>;

  const isAuction = l.sale_type === "auction";
  const isClone = l.product_type === "clone_rights";

  async function placeBid() {
    setErr("");
    try {
      const updated = await api.bid(l.id, parseFloat(bid));
      setL(updated); setBid(""); setToast("Bid placed!");
      setTimeout(() => setToast(""), 2500);
    } catch (e: any) { setErr(e.message); }
  }

  async function buyNow() {
    setErr("");
    try {
      const res = await api.buyIntent(l.id);
      if (res.dev_mode) { setToast("Test order created (Stripe not fully live)."); setTimeout(() => setToast(""), 2500); return; }
      setCheckout({ secret: res.client_secret, label: money(res.buyer_total_cents / 100, l.currency) });
    } catch (e: any) { setErr(e.message); }
  }

  function share() {
    const url = typeof window !== "undefined" ? window.location.href : "";
    if (navigator.share) navigator.share({ title: l.title, url }).catch(() => {});
    else { navigator.clipboard.writeText(url); setToast("Link copied!"); setTimeout(() => setToast(""), 2000); }
  }

  const total = isClone && l.lab_production_cost ? (l.unit_price || 0) + l.lab_production_cost : null;

  return (
    <div className="container section">
      <div className="grid" style={{ gridTemplateColumns: "1fr", gap: 30 }}>
        <div className="grid" style={{ gridTemplateColumns: "minmax(0,1fr)", gap: 30 }}>
          <div style={{ display: "grid", gap: 30, gridTemplateColumns: "1fr" }}>
            <div className="row wrap" style={{ alignItems: "flex-start", gap: 30 }}>
              {/* Media */}
              <div style={{ flex: "1 1 320px", minWidth: 280 }}>
                <div className="card lc-media" style={{ aspectRatio: "4/3" }}>
                  {l.photo_url ? <img src={l.photo_url} alt={l.title} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                    : <span className="glyph">{PRODUCT_GLYPH[l.product_type]}</span>}
                </div>
                {l.video_embed_url && (
                  <div className="card" style={{ marginTop: 14, aspectRatio: "16/9" }}>
                    <iframe src={l.video_embed_url} style={{ width: "100%", height: "100%", border: 0 }} allowFullScreen />
                  </div>
                )}
              </div>

              {/* Buy box */}
              <div style={{ flex: "1 1 340px", minWidth: 300 }}>
                <div className="row" style={{ gap: 6, marginBottom: 10 }}>
                  <span className="pill pill-dim">{PRODUCT_LABEL[l.product_type]}</span>
                  {isAuction && <span className="pill pill-red">{l.no_reserve ? "No Reserve" : "Auction"}</span>}
                  {l.exclusive && <span className="pill">Exclusive</span>}
                  {l.featured && <span className="pill">★ Featured</span>}
                </div>
                <h1 style={{ fontSize: "1.7rem" }}>{l.title}</h1>

                <div className="card card-pad" style={{ marginTop: 16 }}>
                  <div className="big-price">
                    {money(isAuction ? l.current_bid ?? l.start_price : l.unit_price, l.currency)}
                    <span className="faint" style={{ fontSize: "0.9rem", fontWeight: 500 }}>
                      {" "}{isAuction ? "current bid" : isClone ? "rights fee" : l.product_type === "semen" ? "/ straw" : "/ embryo"}
                    </span>
                  </div>

                  {isClone && l.lab_production_cost != null && (
                    <div style={{ marginTop: 12 }}>
                      <div className="kv"><span className="k">Rights fee (to seller)</span><span>{money(l.unit_price, l.currency)}</span></div>
                      <div className="kv"><span className="k">Est. lab production (to cloning facility)</span><span>{money(l.lab_production_cost, l.currency)}</span></div>
                      <div className="kv" style={{ fontWeight: 700 }}><span>Estimated all-in</span><span className="gold">{money(total, l.currency)}</span></div>
                      <p className="help">A clone is a live birth via surrogate, produced months later at the cloning facility (typical success ~80%). You license the rights here; production is arranged with the facility.</p>
                    </div>
                  )}

                  <div className="faint" style={{ margin: "10px 0", fontSize: "0.88rem" }}>{l.quantity_display}</div>

                  {isAuction ? (
                    <div className="stack">
                      <div className="row">
                        <input className="input" placeholder="Your bid" value={bid} onChange={(e) => setBid(e.target.value)} inputMode="decimal" />
                        <button className="btn btn-gold" disabled={!user || !bid} onClick={placeBid}>Place bid</button>
                      </div>
                      {!user && <p className="help">Sign in and add a payment method to bid.</p>}
                    </div>
                  ) : (
                    <button className="btn btn-gold btn-block btn-lg" disabled={!user} onClick={buyNow}>
                      {user ? "Buy now" : "Sign in to buy"}
                    </button>
                  )}
                  {!isAuction && <p className="help">Buyer covers card processing (shown at checkout). You pay the facility for shipping at cost.</p>}
                  <button className="btn btn-block" style={{ marginTop: 10 }} onClick={share}>↗ Share</button>
                  {err && <p className="help" style={{ color: "var(--red)" }}>{err}</p>}
                </div>
              </div>
            </div>

            {/* Details */}
            <div className="row wrap" style={{ alignItems: "flex-start", gap: 30 }}>
              <div style={{ flex: "1 1 340px" }}>
                <h2 style={{ fontSize: "1.2rem" }}>About this listing</h2>
                <p className="muted">{l.description}</p>
                {(l.animal_reg || l.sire_reg) && (
                  <p style={{ marginTop: 14 }}>
                    <Link className="btn" href={`/animal/${encodeURIComponent(l.animal_reg || l.sire_reg)}`}>
                      🧬 View pedigree & registry record →
                    </Link>
                  </p>
                )}
              </div>
              <div style={{ flex: "1 1 300px" }}>
                <h2 style={{ fontSize: "1.2rem" }}>Storage & shipping</h2>
                <div className="kv"><span className="k">Who ships</span><span>Storage facility, on seller's release</span></div>
                <div className="kv"><span className="k">Shipping cost</span><span>{l.who_pays_shipping === "buyer" ? "Buyer pays at cost" : l.who_pays_shipping}</span></div>
                {l.export_eligibility?.length ? (
                  <div className="kv"><span className="k">Export-eligible</span><span>{l.export_eligibility.join(", ")}</span></div>
                ) : null}
                <p className="help">Frozen genetics stay in the facility's tank and ship tank-to-tank or in an IATA dry shipper. Buyer confirms a receiving account at checkout.</p>
              </div>
            </div>
          </div>
        </div>
      </div>
      {toast && <div className="toast">{toast}</div>}
      {checkout && (
        <Checkout
          clientSecret={checkout.secret}
          amountLabel={checkout.label}
          onClose={() => setCheckout(null)}
          onSuccess={() => { setCheckout(null); setToast("Purchase complete! 🎉"); load(); setTimeout(() => setToast(""), 3000); }}
        />
      )}
    </div>
  );
}
