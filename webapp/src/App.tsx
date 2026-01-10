import { useEffect } from "react";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { authInfo } from "./api/client";
import { BottomNav } from "./components/BottomNav";
import { TelegramDiagnosticsBanner } from "./components/TelegramDiagnosticsBanner";
import { AdPage } from "./pages/AdPage";
import { FavoritesPage } from "./pages/FavoritesPage";
import { HomePage } from "./pages/HomePage";
import { PremiumPage } from "./pages/PremiumPage";
import { ProfilePage } from "./pages/ProfilePage";
import { TitlePage } from "./pages/TitlePage";
import { TelegramInitDataProvider, telegramEnv, useTelegramInitData } from "./state/telegramInitData";
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
  const { initDataLen, refreshInitData, isChecking } = useTelegramInitData();

  useEffect(() => {
    refreshFavorites().catch(() => null);
    refreshSubscriptions().catch(() => null);
  }, [refreshFavorites, refreshSubscriptions]);

  return (
    <div
      className="app-shell"
      style={telegramEnv.diagnosticsEnabled ? { paddingTop: "92px" } : undefined}
    >
      <TelegramDiagnosticsBanner />
      <TopBar />
      {initDataLen === 0 && (
        <div className="main-content" style={{ paddingBottom: 0 }}>
          <div className="card">
            <p className="meta">
              Не удалось получить initData. Откройте WebApp из Telegram или нажмите
              “Повторить”.
            </p>
            <button
              type="button"
              className="button"
              onClick={() => refreshInitData().catch(() => null)}
              disabled={isChecking}
            >
              {isChecking ? "Проверяем..." : "Повторить проверку"}
            </button>
          </div>
        </div>
      )}
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/title/:id" element={<TitlePage />} />
        <Route path="/ad" element={<AdPage />} />
        <Route path="/favorites" element={<FavoritesPage />} />
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

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const startapp = params.get("startapp");
    const refFromStartapp =
      startapp && startapp.startsWith("ref_") ? startapp.replace("ref_", "") : null;
    const ref = params.get("ref") || refFromStartapp;
    if (ref) {
      localStorage.setItem("kina_referral_code", ref);
    }
  }, []);

  return (
    <BrowserRouter>
      <TelegramInitDataProvider>
        <UserDataProvider>
          <WatchProvider>
            <AppLayout />
          </WatchProvider>
        </UserDataProvider>
      </TelegramInitDataProvider>
    </BrowserRouter>
  );
}
