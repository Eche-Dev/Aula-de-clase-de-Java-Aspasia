import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  apiGet,
  apiSend,
  clearSession,
  getAccessToken,
  setSession,
  type TokenPayload,
  type UserPublic,
} from "../../lib/api";

type AuthState = {
  isAuthenticated: boolean;
  mustChange: boolean;
  user: UserPublic | null;
  loginStudent: (input: {
    course_code: string;
    identifier: string;
    pin: string;
  }) => Promise<TokenPayload>;
  loginStaff: (input: { email: string; password: string }) => Promise<TokenPayload>;
  /** Tras verificar el código TOTP del reto 2FA de super_admin (Fase D). */
  finishMfaLogin: (input: { access_token: string; must_change_credentials: boolean }) => void;
  changeCredentials: (input: { current_secret: string; new_secret: string }) => Promise<void>;
  refreshUser: () => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

function initialAuth(): { isAuthenticated: boolean; mustChange: boolean } {
  const token = localStorage.getItem("aula.access_token");
  return {
    isAuthenticated: Boolean(token),
    mustChange: localStorage.getItem("aula.must_change") === "1",
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState(initialAuth);
  const [user, setUser] = useState<UserPublic | null>(null);

  useEffect(() => {
    if (!state.isAuthenticated || state.mustChange || !getAccessToken()) {
      return;
    }
    let cancelled = false;
    void apiGet<UserPublic>("/auth/me")
      .then((profile) => {
        if (!cancelled) setUser(profile);
      })
      .catch(() => {
        if (!cancelled) setUser(null);
      });
    return () => {
      cancelled = true;
    };
  }, [state.isAuthenticated, state.mustChange]);

  const loginStudent = useCallback(
    async (input: { course_code: string; identifier: string; pin: string }) => {
      const tokens = await apiSend<TokenPayload>("POST", "/auth/login/student", input);
      setSession(tokens, "student");
      setState({ isAuthenticated: true, mustChange: tokens.must_change_credentials });
      return tokens;
    },
    [],
  );

  const loginStaff = useCallback(async (input: { email: string; password: string }) => {
    const tokens = await apiSend<TokenPayload>("POST", "/auth/login/staff", input);
    // Reto 2FA de super_admin: NO hay sesión hasta verificar el TOTP
    if (tokens.mfa_required) return tokens;
    setSession(tokens, "staff");
    setState({ isAuthenticated: true, mustChange: tokens.must_change_credentials });
    return tokens;
  }, []);

  const finishMfaLogin = useCallback(
    (input: { access_token: string; must_change_credentials: boolean }) => {
      setSession(input, "staff");
      setState({ isAuthenticated: true, mustChange: input.must_change_credentials });
    },
    [],
  );

  const changeCredentials = useCallback(
    async (input: { current_secret: string; new_secret: string }) => {
      await apiSend("PATCH", "/auth/change-credentials", input);
      localStorage.setItem("aula.must_change", "0");
      setState((prev) => ({ ...prev, mustChange: false }));
    },
    [],
  );

  const refreshUser = useCallback(async () => {
    if (!getAccessToken()) return;
    try {
      const profile = await apiGet<UserPublic>("/auth/me");
      setUser(profile);
    } catch {
      setUser(null);
    }
  }, []);

  const logout = useCallback(() => {
    void apiSend("POST", "/auth/logout", {}).catch(() => undefined);
    clearSession();
    setUser(null);
    setState({ isAuthenticated: false, mustChange: false });
  }, []);

  const value = useMemo(
    () => ({
      isAuthenticated: state.isAuthenticated,
      mustChange: state.mustChange,
      user,
      loginStudent,
      loginStaff,
      finishMfaLogin,
      changeCredentials,
      refreshUser,
      logout,
    }),
    [
      state.isAuthenticated,
      state.mustChange,
      user,
      loginStudent,
      loginStaff,
      finishMfaLogin,
      changeCredentials,
      refreshUser,
      logout,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
