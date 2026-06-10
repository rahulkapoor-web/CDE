import { useState, useEffect } from "react";

export function useAuth() {
  const [token, setToken] = useState<string | null>(
    localStorage.getItem("token")
  );

  const isAuthenticated = !!token;

  const loginUser = (newToken: string) => {
    localStorage.setItem("token", newToken);
    setToken(newToken);
  };

  const logout = () => {
    localStorage.removeItem("token");
    setToken(null);
  };

  return { isAuthenticated, token, loginUser, logout };
}
