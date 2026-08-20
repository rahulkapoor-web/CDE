import { createContext, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { User } from "../types";
import { authApi } from "../services/api";

interface AuthContextValue {
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function readStoredUser(): User | null {
  // Only treat the session as valid if BOTH the token and user are present.
  const token = localStorage.getItem("token");
  const stored = localStorage.getItem("user");
  if (!token || !stored) return null;
  try {
    return JSON.parse(stored) as User;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  // Initialize synchronously from localStorage so the very first render already
  // has the restored session. Otherwise route guards see null on refresh and
  // redirect to /login before an effect can restore it.
  const [user, setUser] = useState<User | null>(() => readStoredUser());

  function persist(token: string, u: User) {
    localStorage.setItem("token", token);
    localStorage.setItem("user", JSON.stringify(u));
    setUser(u);
  }

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      async login(email, password) {
        const res = await authApi.login(email, password);
        persist(res.access_token, res.user);
      },
      async register(email, password, fullName) {
        const res = await authApi.register(email, password, fullName);
        persist(res.access_token, res.user);
      },
      logout() {
        localStorage.removeItem("token");
        localStorage.removeItem("user");
        setUser(null);
      },
    }),
    [user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
