import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { api } from "../api/client";
import type { AuthResponse, ReferralInfo, Title } from "../api/types";

interface UserDataContextValue {
  favorites: Title[];
  favoriteIds: Set<number>;
  subscriptions: Set<number>;
  user: AuthResponse | null;
  premiumUntil: string | null;
  premiumActive: boolean;
  referral: ReferralInfo | null;
  refreshFavorites: () => Promise<void>;
  refreshSubscriptions: () => Promise<void>;
  refreshAuth: () => Promise<void>;
  refreshReferral: () => Promise<void>;
  toggleFavorite: (titleId: number) => Promise<void>;
  toggleSubscription: (titleId: number) => Promise<void>;
}

const UserDataContext = createContext<UserDataContextValue | undefined>(undefined);

export const UserDataProvider = ({ children }: { children: React.ReactNode }) => {
  const [favorites, setFavorites] = useState<Title[]>([]);
  const [subscriptions, setSubscriptions] = useState<Set<number>>(new Set());
  const [user, setUser] = useState<AuthResponse | null>(null);
  const [premiumUntil, setPremiumUntil] = useState<string | null>(null);
  const [premiumActive, setPremiumActive] = useState(false);
  const [referral, setReferral] = useState<ReferralInfo | null>(null);

  const refreshFavorites = useCallback(async () => {
    const data = await api.getFavorites();
    setFavorites(data);
  }, []);

  const refreshSubscriptions = useCallback(async () => {
    const data = await api.getSubscriptions();
    setSubscriptions(new Set(data.filter((item) => item.enabled).map((item) => item.title_id)));
  }, []);

  const toggleFavorite = useCallback(async (titleId: number) => {
    await api.toggleFavorite(titleId);
    await refreshFavorites();
  }, [refreshFavorites]);

  const toggleSubscription = useCallback(
    async (titleId: number) => {
      await api.toggleSubscription(titleId);
      await refreshSubscriptions();
    },
    [refreshSubscriptions],
  );

  const refreshAuth = useCallback(async () => {
    const storedRef =
      typeof window === "undefined" ? null : localStorage.getItem("kina_referral_code");
    const data = await api.authWebapp(storedRef);
    setUser(data);
    setPremiumUntil(data.premium_until);
    if (data.premium_until) {
      setPremiumActive(new Date(data.premium_until) > new Date());
    } else {
      setPremiumActive(false);
    }
    if (storedRef) {
      localStorage.removeItem("kina_referral_code");
    }
  }, []);

  const refreshReferral = useCallback(async () => {
    const data = await api.getReferralMe();
    setReferral(data);
  }, []);

  useEffect(() => {
    refreshAuth().catch(() => null);
  }, [refreshAuth]);

  const favoriteIds = useMemo(
    () => new Set(favorites.map((favorite) => favorite.id)),
    [favorites],
  );

  const value = useMemo(
    () => ({
      favorites,
      favoriteIds,
      subscriptions,
      user,
      premiumUntil,
      premiumActive,
      referral,
      refreshFavorites,
      refreshSubscriptions,
      refreshAuth,
      refreshReferral,
      toggleFavorite,
      toggleSubscription,
    }),
    [
      favorites,
      favoriteIds,
      subscriptions,
      user,
      premiumUntil,
      premiumActive,
      referral,
      refreshFavorites,
      refreshSubscriptions,
      refreshAuth,
      refreshReferral,
      toggleFavorite,
      toggleSubscription,
    ],
  );

  return <UserDataContext.Provider value={value}>{children}</UserDataContext.Provider>;
};

export const useUserData = () => {
  const context = useContext(UserDataContext);
  if (!context) {
    throw new Error("useUserData must be used within UserDataProvider");
  }
  return context;
};
