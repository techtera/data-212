'use client';

import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react';
import { getMe } from './api';

interface User {
  id: string;
  username: string;
  email: string;
}

interface AuthContextType {
  token: string | null;
  user: User | null;
  loading: boolean;
  login: (token: string, user: User) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  token: null,
  user: null,
  loading: true,
  login: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem('token');
    if (stored) {
      getMe(stored)
        .then((u) => {
          setToken(stored);
          setUser(u);
        })
        .catch(() => {
          localStorage.removeItem('token');
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const loginFn = useCallback((t: string, u: User) => {
    localStorage.setItem('token', t);
    setToken(t);
    setUser(u);
  }, []);

  const logoutFn = useCallback(() => {
    localStorage.removeItem('token');
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ token, user, loading, login: loginFn, logout: logoutFn }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
