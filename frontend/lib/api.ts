export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8100";

function token(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("wt_token");
}

async function req(path: string, opts: RequestInit = {}): Promise<any> {
  const headers: Record<string, string> = { ...(opts.headers as any) };
  if (opts.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const t = token();
  if (t) headers["Authorization"] = `Bearer ${t}`;
  const res = await fetch(`${API_BASE}${path}`, { ...opts, headers });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const j = await res.json();
      detail = j.detail || detail;
    } catch {}
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  // auth
  register: (body: any) => req("/api/auth/register", { method: "POST", body: JSON.stringify(body) }),
  login: async (email: string, password: string) => {
    const form = new URLSearchParams({ username: email, password });
    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form,
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Login failed");
    return res.json();
  },
  me: () => req("/api/auth/me"),
  becomeSeller: () => req("/api/users/me/become-seller", { method: "POST" }),
  updateMe: (body: any) => req("/api/users/me", { method: "PATCH", body: JSON.stringify(body) }),

  // animals / registry
  lookupAnimal: (q: string) => req(`/api/animals/lookup?q=${encodeURIComponent(q)}`),
  suggestAnimals: (q: string) => req(`/api/animals/suggest?q=${encodeURIComponent(q)}`),
  foundation: (bloodline?: string) =>
    req(`/api/animals/foundation${bloodline ? `?bloodline=${encodeURIComponent(bloodline)}` : ""}`),
  animal: (reg: string) => req(`/api/animals/${encodeURIComponent(reg)}`),
  animalOffers: (reg: string) => req(`/api/animals/${encodeURIComponent(reg)}/offers`),

  // facilities
  facilities: (q?: string) => req(`/api/facilities${q ? `?q=${encodeURIComponent(q)}` : ""}`),

  // listings
  browse: (params: Record<string, any> = {}) =>
    req(`/api/listings?${new URLSearchParams(clean(params))}`),
  listing: (id: number | string) => req(`/api/listings/${id}`),
  myListings: () => req("/api/listings/mine"),
  createListing: (body: any) => req("/api/listings", { method: "POST", body: JSON.stringify(body) }),
  bid: (id: number, amount: number) =>
    req(`/api/listings/${id}/bid`, { method: "POST", body: JSON.stringify({ amount }) }),
  feature: (id: number, days = 7) => req(`/api/listings/${id}/feature?days=${days}`, { method: "POST" }),
  adCopy: (body: any) => req("/api/listings/ai/ad-copy", { method: "POST", body: JSON.stringify(body) }),

  // search
  search: (params: Record<string, any> = {}) =>
    req(`/api/search?${new URLSearchParams(clean(params))}`),
  facets: () => req("/api/search/facets"),

  // payments
  paymentsConfig: () => req("/api/payments/config"),
  quote: (listingId: number | string) => req(`/api/payments/quote/${listingId}`),
  onboard: () => req("/api/payments/connect/onboard", { method: "POST" }),
  buyIntent: (listingId: number) => req(`/api/payments/buy/${listingId}`, { method: "POST" }),
  featureIntent: (listingId: number, days = 7) =>
    req(`/api/payments/feature/${listingId}?days=${days}`, { method: "POST" }),

  // screenshot -> pedigree extraction
  extractPedigree: async (fileFieldForm: FormData) => {
    const t = typeof window !== "undefined" ? localStorage.getItem("wt_token") : null;
    const res = await fetch(`${API_BASE}/api/animals/extract`, {
      method: "POST",
      headers: t ? { Authorization: `Bearer ${t}` } : {},
      body: fileFieldForm,
    });
    if (!res.ok) throw new Error("Extraction failed");
    return res.json();
  },

  // storefront + content
  storefront: (handle: string) => req(`/api/users/${encodeURIComponent(handle)}`),
  breedHistory: () => req("/api/content/breed-history"),
};

function clean(p: Record<string, any>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(p)) {
    if (v !== undefined && v !== null && v !== "") out[k] = String(v);
  }
  return out;
}

export const PRODUCT_GLYPH: Record<string, string> = {
  semen: "🧬",
  embryo: "🥚",
  clone_rights: "🐂",
};
export const PRODUCT_LABEL: Record<string, string> = {
  semen: "Semen",
  embryo: "Embryo",
  clone_rights: "Cloning Rights",
};

export function money(n: number | null | undefined, ccy = "USD"): string {
  if (n === null || n === undefined) return "—";
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: ccy, maximumFractionDigits: 0 }).format(n);
  } catch {
    return `$${n}`;
  }
}
