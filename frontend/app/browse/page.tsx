"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { api, PRODUCT_LABEL } from "../../lib/api";
import ListingCard from "../../components/ListingCard";

function BrowseInner() {
  const sp = useSearchParams();
  const router = useRouter();
  const [facets, setFacets] = useState<any>(null);
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const filters = {
    q: sp.get("q") || "",
    product_type: sp.get("product_type") || "",
    bloodline: sp.get("bloodline") || "",
    sale_type: sp.get("sale_type") || "",
    export: sp.get("export") || "",
    sort: sp.get("sort") || "newest",
  };

  useEffect(() => { api.facets().then(setFacets).catch(() => {}); }, []);

  useEffect(() => {
    setLoading(true);
    api.search(filters).then(setResults).catch(() => setResults([])).finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sp.toString()]);

  function setParam(key: string, val: string) {
    const p = new URLSearchParams(sp.toString());
    if (val) p.set(key, val); else p.delete(key);
    router.push(`/browse?${p.toString()}`);
  }

  return (
    <div className="container section">
      <h1 style={{ fontSize: "1.8rem" }}>
        Browse {filters.product_type ? PRODUCT_LABEL[filters.product_type] : "genetics"}
      </h1>

      <div className="row wrap" style={{ gap: 10, margin: "18px 0 24px" }}>
        <select className="select" style={{ width: "auto" }} value={filters.product_type} onChange={(e) => setParam("product_type", e.target.value)}>
          <option value="">All products</option>
          {(facets?.product_types || []).map((p: string) => <option key={p} value={p}>{PRODUCT_LABEL[p] || p}</option>)}
        </select>
        <select className="select" style={{ width: "auto" }} value={filters.bloodline} onChange={(e) => setParam("bloodline", e.target.value)}>
          <option value="">All bloodlines</option>
          {(facets?.bloodlines || []).map((b: string) => <option key={b} value={b}>{b}</option>)}
        </select>
        <select className="select" style={{ width: "auto" }} value={filters.sale_type} onChange={(e) => setParam("sale_type", e.target.value)}>
          <option value="">Fixed & auction</option>
          <option value="fixed">Buy now</option>
          <option value="auction">Auctions</option>
        </select>
        <select className="select" style={{ width: "auto" }} value={filters.export} onChange={(e) => setParam("export", e.target.value)}>
          <option value="">Any destination</option>
          {(facets?.export_regions || []).map((r: string) => <option key={r} value={r}>Export to {r}</option>)}
        </select>
        <div className="spacer" />
        <select className="select" style={{ width: "auto" }} value={filters.sort} onChange={(e) => setParam("sort", e.target.value)}>
          <option value="newest">Newest</option>
          <option value="price_asc">Price ↑</option>
          <option value="price_desc">Price ↓</option>
          <option value="ending_soon">Ending soon</option>
        </select>
      </div>

      {loading ? (
        <div className="grid listings-grid">{Array.from({ length: 8 }).map((_, i) => <div key={i} className="card"><div className="lc-media" /><div className="lc-body"><div className="skeleton" style={{ width: "70%" }} /></div></div>)}</div>
      ) : results.length ? (
        <div className="grid listings-grid">{results.map((l) => <ListingCard key={l.id} l={l} />)}</div>
      ) : (
        <div className="adslot">No results match those filters. Try widening your search.</div>
      )}
    </div>
  );
}

export default function Browse() {
  return (
    <Suspense fallback={<div className="container section">Loading…</div>}>
      <BrowseInner />
    </Suspense>
  );
}
