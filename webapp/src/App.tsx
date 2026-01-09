import { useEffect } from "react";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { authInfo } from "./api/client";
import { BottomNav } from "./components/BottomNav";
import { AdPage } from "./pages/AdPage";
import { HomePage } from "./pages/HomePage";
import { PremiumPage } from "./pages/PremiumPage";
import { ProfilePage } from "./pages/ProfilePage";
import { TitlePage } from "./pages/TitlePage";
import { UserDataProvider, useUserData } from "./state/userData";
import { WatchProvider } from "./state/watchFlow";

const TopBar = () => {
  const location = useLocation();
  const label =
    location.pathname === "/"
      ? "Kina • Home"
      : location.pathname.startsWith("/title")
        ? "Kina • Title"
        : location.pathname === "/ad"
          ? "Kina • Ads"
          : location.pathname === "/premium"
            ? "Kina • Premium"
            : "Kina • Profile";
  return (
    <header className="topbar">
      <h1>{label}</h1>
      {authInfo.initData ? <span className="pill">Telegram</span> : <span className="pill">DEV</span>}
    </header>
  );
};

const AppLayout = () => {
  const { refreshFavorites, refreshSubscriptions } = useUserData();

  useEffect(() => {
    refreshFavorites().catch(() => null);
    refreshSubscriptions().catch(() => null);
  }, [refreshFavorites, refreshSubscriptions]);

  return (
    <div className="app-shell">
      <TopBar />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/title/:id" element={<TitlePage />} />
        <Route path="/ad" element={<AdPage />} />
        <Route path="/premium" element={<PremiumPage />} />
        <Route path="/profile" element={<ProfilePage />} />
      </Routes>
      <BottomNav />
    </div>
  );
};

export default function App() {
  useEffect(() => {
    const telegram = (window as typeof window & {
      Telegram?: { WebApp?: { ready: () => void; expand: () => void } };
    }).Telegram?.WebApp;
    telegram?.ready();
    telegram?.expand();
  }, []);

  return (
    <BrowserRouter>
      <UserDataProvider>
        <WatchProvider>
          <AppLayout />
        </WatchProvider>
      </UserDataProvider>
    </BrowserRouter>
  );
}
