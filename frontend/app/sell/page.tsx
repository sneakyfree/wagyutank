"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, PRODUCT_LABEL, money } from "../../lib/api";
import { useAuth } from "../../lib/auth";

const PRODUCTS = [
  { key: "semen", glyph: "🧬", label: "Semen", blurb: "Straws from a proven sire" },
  { key: "embryo", glyph: "🥚", label: "Embryos", blurb: "Full-blood sire × dam" },
  { key: "clone_rights", glyph: "🐂", label: "Cloning Rights", blurb: "License a banked cell line" },
];

export default function Sell() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [step, setStep] = useState(0);

  // draft state
  const [productType, setProductType] = useState("");
  const [animalQuery, setAnimalQuery] = useState("");
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [animal, setAnimal] = useState<any>(null);
  const [dam, setDam] = useState<any>(null);
  const [description, setDescription] = useState("");
  const [genErr, setGenErr] = useState("");

  const [form, setForm] = useState<any>({
    sale_type: "fixed", unit_price: "", currency: "USD",
    start_price: "", no_reserve: false, quantity_available: 1,
    quantity_visibility: "in_stock_only", semen_type: "conventional",
    exclusive: false, rights_count: 1, lab_production_cost: "",
    export_eligibility: [] as string[],
  });
  const [facilityQuery, setFacilityQuery] = useState("");
  const [facilities, setFacilities] = useState<any[]>([]);
  const [facility, setFacility] = useState<any>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (animalQuery.length < 2) { setSuggestions([]); return; }
    const t = setTimeout(() => api.suggestAnimals(animalQuery).then(setSuggestions).catch(() => {}), 200);
    return () => clearTimeout(t);
  }, [animalQuery]);

  useEffect(() => {
    if (facilityQuery.length < 1) { setFacilities([]); return; }
    const t = setTimeout(() => api.facilities(facilityQuery).then(setFacilities).catch(() => {}), 200);
    return () => clearTimeout(t);
  }, [facilityQuery]);

  if (loading) return <div className="container section">Loading…</div>;
  if (!user) return (
    <div className="container section center">
      <h1>List your genetics</h1>
      <p className="muted">Sign in to create a listing — it takes under a minute, and it's free.</p>
      <Link href="/login?next=/sell" className="btn btn-gold btn-lg" style={{ marginTop: 12 }}>Sign in to sell</Link>
    </div>
  );

  const isClone = productType === "clone_rights";
  const isEmbryo = productType === "embryo";
  const isSemen = productType === "semen";

  async function pickAnimal(a: any, which: "sire" | "dam" = "sire") {
    if (which === "dam") { setDam(a); return; }
    setAnimal(a); setSuggestions([]); setAnimalQuery(a.name);
  }

  async function generateAd() {
    setGenErr("");
    try {
      const res = await api.adCopy({
        product_type: productType,
        animal: {
          name: animal?.name || animalQuery,
          registration_no: animal?.registration_no || null,
          bloodline: animal?.bloodline, bloodline_detail: animal?.bloodline_detail,
          breed: animal?.breed, sire_name: isEmbryo ? animal?.name : null,
        },
      });
      setDescription(res.description);
    } catch (e: any) { setGenErr(e.message); }
  }

  function toggleExport(code: string) {
    setForm((f: any) => ({
      ...f,
      export_eligibility: f.export_eligibility.includes(code)
        ? f.export_eligibility.filter((c: string) => c !== code)
        : [...f.export_eligibility, code],
    }));
  }

  async function publish() {
    setSubmitting(true);
    try {
      if (!user!.is_seller) await api.becomeSeller();
      const payload: any = {
        product_type: productType,
        description,
        sale_type: form.sale_type,
        currency: form.currency,
        quantity_available: Number(form.quantity_available) || 1,
        quantity_visibility: form.quantity_visibility,
        export_eligibility: form.export_eligibility,
        storage_facility_id: facility?.id,
      };
      if (isEmbryo) { payload.sire_reg = animal?.registration_no; payload.dam_reg = dam?.registration_no; }
      else { payload.animal_reg = animal?.registration_no; }
      if (isSemen) payload.semen_type = form.semen_type;
      if (isClone) { payload.rights_count = Number(form.rights_count); payload.exclusive = form.exclusive; payload.lab_production_cost = Number(form.lab_production_cost) || null; payload.cloning_facility_id = facility?.id; }
      if (form.sale_type === "fixed") payload.unit_price = Number(form.unit_price);
      else { payload.start_price = Number(form.start_price); payload.no_reserve = form.no_reserve; }

      const listing = await api.createListing(payload);
      router.push(`/listing/${listing.id}`);
    } catch (e: any) { setGenErr(e.message); setSubmitting(false); }
  }

  const steps = ["Product", "Animal", "Ad", "Price", "Storage", "Publish"];

  return (
    <div className="container section" style={{ maxWidth: 720 }}>
      <div className="steps">
        {steps.map((_, i) => <div key={i} className={`step-dot ${i <= step ? "active" : ""}`} />)}
      </div>

      {/* Step 0 — product */}
      {step === 0 && (
        <div>
          <h1>What are you selling?</h1>
          <div className="cats" style={{ marginTop: 20 }}>
            {PRODUCTS.map((p) => (
              <button key={p.key} className="cat" style={{ textAlign: "left", cursor: "pointer" }}
                onClick={() => { setProductType(p.key); setStep(1); }}>
                <div className="glyph">{p.glyph}</div>
                <h3>{p.label}</h3>
                <p className="muted">{p.blurb}</p>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Step 1 — animal */}
      {step === 1 && (
        <div>
          <h1>{isEmbryo ? "Which sire?" : "Which animal?"}</h1>
          <p className="muted">Type the registration number (FB…) or name. Foundation animals fill in instantly.</p>
          <div className="field" style={{ marginTop: 16, position: "relative" }}>
            <input className="input" placeholder="e.g. FB1615 or Michifuku" value={animalQuery}
              onChange={(e) => { setAnimalQuery(e.target.value); setAnimal(null); }} />
            {suggestions.length > 0 && !animal && (
              <div className="card" style={{ position: "absolute", zIndex: 20, width: "100%", marginTop: 4 }}>
                {suggestions.map((s) => (
                  <button key={s.id} className="row" style={{ width: "100%", background: "none", border: "none", borderBottom: "1px solid var(--border-soft)", padding: "10px 14px", cursor: "pointer", color: "var(--text)" }}
                    onClick={() => pickAnimal(s)}>
                    <span style={{ fontWeight: 600 }}>{s.name}</span>
                    <span className="faint" style={{ fontSize: "0.8rem" }}>{s.registration_no} · {s.bloodline}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {animal && (
            <div className="card card-pad" style={{ borderColor: "var(--gold)" }}>
              <div className="row"><span className="pill">Found</span><strong>{animal.name}</strong>
                <span className="faint">{animal.registration_no} · {animal.bloodline}</span></div>
              {animal.notable && <p className="muted" style={{ marginTop: 8, fontSize: "0.9rem" }}>{animal.notable}</p>}
            </div>
          )}

          {!animal && animalQuery.length >= 2 && (
            <p className="help">
              Not one of ours yet? Open your animal's page on the registry, screenshot the pedigree, and we'll read it — or just continue and confirm the details. (Screenshot capture wires in with the vision key.)
            </p>
          )}

          {isEmbryo && animal && (
            <div className="field" style={{ marginTop: 18 }}>
              <label>Dam (optional)</label>
              <input className="input" placeholder="Dam reg # or name"
                onChange={(e) => api.lookupAnimal(e.target.value).then((d) => d && setDam(d)).catch(() => {})} />
              {dam && <p className="help">Dam: <strong className="gold">{dam.name}</strong> ({dam.registration_no})</p>}
            </div>
          )}

          <div className="row" style={{ marginTop: 22 }}>
            <button className="btn" onClick={() => setStep(0)}>Back</button>
            <div className="spacer" />
            <button className="btn btn-gold" disabled={!animal && animalQuery.length < 2}
              onClick={() => { if (!animal && animalQuery) setAnimal({ name: animalQuery, registration_no: null }); setStep(2); }}>
              Continue →
            </button>
          </div>
        </div>
      )}

      {/* Step 2 — ad */}
      {step === 2 && (
        <div>
          <h1>Your ad, written for you</h1>
          <p className="muted">We drafted this from the pedigree. Tweak it, or regenerate.</p>
          <div className="field" style={{ marginTop: 16 }}>
            {!description && (
              <button className="btn btn-gold" onClick={generateAd}>✨ Write my ad</button>
            )}
            {description && (
              <>
                <textarea className="textarea" style={{ minHeight: 160 }} value={description} onChange={(e) => setDescription(e.target.value)} />
                <button className="btn" style={{ marginTop: 8 }} onClick={generateAd}>↻ Regenerate</button>
              </>
            )}
            {genErr && <p className="help" style={{ color: "var(--red)" }}>{genErr}</p>}
          </div>
          <div className="row" style={{ marginTop: 22 }}>
            <button className="btn" onClick={() => setStep(1)}>Back</button>
            <div className="spacer" />
            <button className="btn btn-gold" onClick={() => setStep(3)}>Continue →</button>
          </div>
        </div>
      )}

      {/* Step 3 — price */}
      {step === 3 && (
        <div>
          <h1>Set your price</h1>

          {isSemen && (
            <div className="field"><label>Semen type</label>
              <select className="select" value={form.semen_type} onChange={(e) => setForm({ ...form, semen_type: e.target.value })}>
                <option value="conventional">Conventional</option>
                <option value="sexed_female">Sexed — female</option>
                <option value="sexed_male">Sexed — male</option>
              </select></div>
          )}

          <div className="row wrap" style={{ gap: 12 }}>
            <div className="field" style={{ flex: 1, minWidth: 160 }}>
              <label>Sale type</label>
              <select className="select" value={form.sale_type} onChange={(e) => setForm({ ...form, sale_type: e.target.value })}>
                <option value="fixed">Fixed price</option>
                <option value="auction">Auction</option>
              </select>
            </div>
            <div className="field" style={{ flex: 1, minWidth: 120 }}>
              <label>Currency</label>
              <select className="select" value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })}>
                {["USD", "AUD", "EUR", "GBP", "BRL", "CAD"].map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
          </div>

          {form.sale_type === "fixed" ? (
            <div className="field"><label>{isClone ? "Rights fee" : "Price"} ({isSemen ? "per straw" : isClone ? "per clone right" : "per embryo"})</label>
              <input className="input" inputMode="decimal" value={form.unit_price} onChange={(e) => setForm({ ...form, unit_price: e.target.value })} placeholder="0.00" /></div>
          ) : (
            <div>
              <div className="field"><label>Starting bid</label>
                <input className="input" inputMode="decimal" value={form.start_price} onChange={(e) => setForm({ ...form, start_price: e.target.value })} placeholder="Try $1 for a no-reserve auction" /></div>
              <label className="row" style={{ gap: 8 }}>
                <input type="checkbox" checked={form.no_reserve} onChange={(e) => setForm({ ...form, no_reserve: e.target.checked })} />
                <span>No reserve — sells to the highest bid, no minimum</span>
              </label>
            </div>
          )}

          {isClone && (
            <div className="card card-pad" style={{ marginTop: 8 }}>
              <div className="field"><label>Est. cloning lab production cost (paid by buyer to the facility)</label>
                <input className="input" inputMode="decimal" value={form.lab_production_cost} onChange={(e) => setForm({ ...form, lab_production_cost: e.target.value })} placeholder="e.g. 20000" />
                <p className="help">Buyers see the two-part total: your rights fee + this lab cost.</p>
              </div>
              <label className="row" style={{ gap: 8 }}>
                <input type="checkbox" checked={form.exclusive} onChange={(e) => setForm({ ...form, exclusive: e.target.checked })} />
                <span>Exclusive — the only clone ever made</span>
              </label>
            </div>
          )}

          {!isClone && (
            <div className="row wrap" style={{ gap: 12 }}>
              <div className="field" style={{ flex: 1, minWidth: 140 }}><label>Quantity</label>
                <input className="input" inputMode="numeric" value={form.quantity_available} onChange={(e) => setForm({ ...form, quantity_available: e.target.value })} /></div>
              <div className="field" style={{ flex: 1, minWidth: 180 }}><label>Show quantity as</label>
                <select className="select" value={form.quantity_visibility} onChange={(e) => setForm({ ...form, quantity_visibility: e.target.value })}>
                  <option value="in_stock_only">In stock (hide count)</option>
                  <option value="exact">Exact count</option>
                  <option value="range">Range (10+, 50+…)</option>
                  <option value="hidden">Hidden — contact for availability</option>
                </select></div>
            </div>
          )}

          <div className="row" style={{ marginTop: 16 }}>
            <button className="btn" onClick={() => setStep(2)}>Back</button>
            <div className="spacer" />
            <button className="btn btn-gold" onClick={() => setStep(4)}>Continue →</button>
          </div>
        </div>
      )}

      {/* Step 4 — storage */}
      {step === 4 && (
        <div>
          <h1>{isClone ? "Where is the cell line banked?" : "Where is it stored?"}</h1>
          <p className="muted">{isClone ? "The cloning company holding the banked cell line." : "Your genetics stay put — the facility ships to the buyer, who pays shipping at cost."}</p>
          <div className="field" style={{ marginTop: 16, position: "relative" }}>
            <input className="input" placeholder="Type 'Ha' for Hawkeye…" value={facilityQuery}
              onChange={(e) => { setFacilityQuery(e.target.value); setFacility(null); }} />
            {facilities.length > 0 && !facility && (
              <div className="card" style={{ position: "absolute", zIndex: 20, width: "100%", marginTop: 4 }}>
                {facilities.map((f) => (
                  <button key={f.id} className="row" style={{ width: "100%", background: "none", border: "none", borderBottom: "1px solid var(--border-soft)", padding: "10px 14px", cursor: "pointer", color: "var(--text)" }}
                    onClick={() => { setFacility(f); setFacilityQuery(f.name); setFacilities([]); }}>
                    <span style={{ fontWeight: 600 }}>{f.name}</span>
                    <span className="faint" style={{ fontSize: "0.8rem" }}>{f.city}, {f.state}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          {facility && <p className="help">Stored at <strong className="gold">{facility.name}</strong> — {facility.city}, {facility.state}.</p>}

          {!isClone && (
            <div className="field"><label>Export-eligible destinations (optional)</label>
              <div className="row wrap" style={{ gap: 8 }}>
                {["AUS", "EU", "CAN", "US"].map((c) => (
                  <button key={c} className={`pill ${form.export_eligibility.includes(c) ? "" : "pill-dim"}`} style={{ cursor: "pointer" }} onClick={() => toggleExport(c)}>{c}</button>
                ))}
              </div>
            </div>
          )}

          <div className="row" style={{ marginTop: 16 }}>
            <button className="btn" onClick={() => setStep(3)}>Back</button>
            <div className="spacer" />
            <button className="btn btn-gold" onClick={() => setStep(5)}>Review →</button>
          </div>
        </div>
      )}

      {/* Step 5 — publish */}
      {step === 5 && (
        <div>
          <h1>Ready to publish</h1>
          <div className="card card-pad" style={{ marginTop: 12 }}>
            <div className="kv"><span className="k">Product</span><span>{PRODUCT_LABEL[productType]}</span></div>
            <div className="kv"><span className="k">Animal</span><span>{animal?.name}{isEmbryo && dam ? ` × ${dam.name}` : ""}</span></div>
            <div className="kv"><span className="k">Sale</span><span>{form.sale_type === "fixed" ? `Buy now — ${money(Number(form.unit_price), form.currency)}` : `Auction from ${money(Number(form.start_price), form.currency)}${form.no_reserve ? " · no reserve" : ""}`}</span></div>
            {isClone && form.lab_production_cost && <div className="kv"><span className="k">All-in for buyer</span><span className="gold">{money(Number(form.unit_price) + Number(form.lab_production_cost), form.currency)}</span></div>}
            <div className="kv"><span className="k">Storage</span><span>{facility?.name || "—"}</span></div>
          </div>
          <p className="help" style={{ marginTop: 10 }}>By publishing you confirm you own or are authorized to sell these genetics and that the pedigree is accurate.</p>
          {genErr && <p className="help" style={{ color: "var(--red)" }}>{genErr}</p>}
          <div className="row" style={{ marginTop: 16 }}>
            <button className="btn" onClick={() => setStep(4)}>Back</button>
            <div className="spacer" />
            <button className="btn btn-gold btn-lg" disabled={submitting} onClick={publish}>
              {submitting ? "Publishing…" : "Publish listing →"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
