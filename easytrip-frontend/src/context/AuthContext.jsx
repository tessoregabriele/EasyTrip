import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { getAccessToken, setTokens, clearTokens } from '../api/client';
import { login as loginRequest, register as registerRequest, getMe } from '../api/auth';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!getAccessToken()) {
      setLoading(false);
      return;
    }
    getMe()
      .then(setUser)
      .catch(() => clearTokens())
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (username, password) => {
    const tokens = await loginRequest(username, password);
    setTokens(tokens);
    const me = await getMe();
    setUser(me);
    return me;
  }, []);

  const register = useCallback(
    async (payload) => {
      await registerRequest(payload);
      return login(payload.username, payload.password);
    },
    [login]
  );

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
  }, []);

  const value = {
    user,
    setUser,
    loading,
    isAuthenticated: !!user,
    login,
    register,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth deve essere usato dentro un AuthProvider');
  }
  return ctx;
}
