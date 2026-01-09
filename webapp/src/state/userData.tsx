import React, { createContext, useCallback, useContext, useMemo, useState } from "react";
import { api } from "../api/client";
import type { Title } from "../api/types";

interface UserDataContextValue {
  favorites: Title[];
  favoriteIds: Set<number>;
  subscriptions: Set<number>;
  refreshFavorites: () => Promise<void>;
  refreshSubscriptions: () => Promise<void>;
  toggleFavorite: (titleId: number) => Promise<void>;
  toggleSubscription: (titleId: number) => Promise<void>;
}

const UserDataContext = createContext<UserDataContextValue | undefined>(undefined);

export const UserDataProvider = ({ children }: { children: React.ReactNode }) => {
  const [favorites, setFavorites] = useState<Title[]>([]);
  const [subscriptions, setSubscriptions] = useState<Set<number>>(new Set());

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

  const favoriteIds = useMemo(
    () => new Set(favorites.map((favorite) => favorite.id)),
    [favorites],
  );

  const value = useMemo(
    () => ({
      favorites,
      favoriteIds,
      subscriptions,
      refreshFavorites,
      refreshSubscriptions,
      toggleFavorite,
      toggleSubscription,
    }),
    [
      favorites,
      favoriteIds,
      subscriptions,
      refreshFavorites,
      refreshSubscriptions,
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
