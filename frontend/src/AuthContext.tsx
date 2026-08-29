import { createContext, useContext, useState, type ReactNode } from "react";
import { api, getToken, setToken } from "./api";

interface AuthCtx {
  token: string | null;
  role: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTok] = useState<string | null>(getToken());
  const [role, setRole] = useState<string | null>(localStorage.getItem("fg_role"));

  async function login(email: string, password: string) {
    const res = await api.login(email, password);
    setToken(res.access_token);
    localStorage.setItem("fg_role", res.role);
    setTok(res.access_token);
    setRole(res.role);
  }

  function logout() {
    setToken(null);
    localStorage.removeItem("fg_role");
    setTok(null);
    setRole(null);
  }

  return <Ctx.Provider value={{ token, role, login, logout }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
