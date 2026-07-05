"use client";
import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api } from "./api";

type User = {
  id: number;
  display_name: string;
  handle: string | null;
  email: string;
  is_seller: boolean;
  seller_rating: number;
  seller_rating_count: number;
};

type AuthCtx = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (body: any) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
};

const Ctx = createContext<AuthCtx>(null as any);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    try {
      const me = await api.me();
      setUser(me);
    } catch {
      setUser(null);
    }
  }

  useEffect(() => {
    const t = typeof window !== "undefined" ? localStorage.getItem("wt_token") : null;
    if (!t) { setLoading(false); return; }
    refresh().finally(() => setLoading(false));
  }, []);

  function persist(res: any) {
    localStorage.setItem("wt_token", res.access_token);
    setUser(res.user);
  }

  const value: AuthCtx = {
    user,
    loading,
    login: async (email, password) => persist(await api.login(email, password)),
    register: async (body) => persist(await api.register(body)),
    logout: () => { localStorage.removeItem("wt_token"); setUser(null); },
    refresh,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
