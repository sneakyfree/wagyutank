"use client";
import Link from "next/link";
import { PRODUCT_GLYPH, PRODUCT_LABEL, money } from "../lib/api";

export default function ListingCard({ l }: { l: any }) {
  const isAuction = l.sale_type === "auction";
  const price = isAuction ? l.current_bid ?? l.start_price : l.unit_price;
  return (
    <Link href={`/listing/${l.id}`} className="card">
      <div className="lc-media">
        {l.photo_url ? (
          <img src={l.photo_url} alt={l.title} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        ) : (
          <span className="glyph">{PRODUCT_GLYPH[l.product_type] || "🧬"}</span>
        )}
        {l.featured && <span className="pill badge-featured">★ Featured</span>}
      </div>
      <div className="lc-body">
        <div className="row" style={{ gap: 6, marginBottom: 8 }}>
          <span className="pill pill-dim">{PRODUCT_LABEL[l.product_type]}</span>
          {isAuction && <span className="pill pill-red">{l.no_reserve ? "No Reserve" : "Auction"}</span>}
          {l.exclusive && <span className="pill">Exclusive</span>}
        </div>
        <div className="lc-title">{l.title}</div>
        <div className="row">
          <div>
            <div className="lc-price">{money(price, l.currency)}</div>
            <div className="faint" style={{ fontSize: "0.78rem" }}>
              {isAuction ? "current bid" : l.product_type === "semen" ? "per straw" : l.product_type === "clone_rights" ? "rights fee" : "per embryo"}
            </div>
          </div>
          <div className="spacer" />
          <div className="faint" style={{ fontSize: "0.78rem", textAlign: "right" }}>{l.quantity_display}</div>
        </div>
      </div>
    </Link>
  );
}
