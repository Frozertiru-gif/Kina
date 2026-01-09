import { useEffect } from "react";
import { authInfo } from "../api/client";
import { useUserData } from "../state/userData";

export const ProfilePage = () => {
  const { referral, refreshReferral, premiumActive, premiumUntil, user } = useUserData();

  useEffect(() => {
    refreshReferral().catch(() => null);
  }, [refreshReferral]);

  const handleCopy = async (value: string) => {
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return;
    }
    window.prompt("Скопируйте ссылку", value);
  };

  return (
    <div className="main-content">
      <div className="card">
        <h2 className="section-title">Профиль</h2>
        <div className="notice">Здесь будут настройки уведомлений, языка и подписки.</div>
        <div className="field-row">
          <div className="status-pill">InitData: {authInfo.initData ? "OK" : "—"}</div>
          {authInfo.devUserId && (
            <div className="status-pill">DEV ID: {authInfo.devUserId}</div>
          )}
          {user?.tg_user_id && (
            <div className="status-pill">TG ID: {user.tg_user_id}</div>
          )}
        </div>
        <div className="field-row">
          <div className="status-pill">
            Premium: {premiumActive ? "Active" : "Not active"}
          </div>
          {premiumUntil && (
            <div className="status-pill">
              До {new Date(premiumUntil).toLocaleString()}
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <h3 className="section-title">Пригласить друга</h3>
        <p className="meta">
          Делитесь ссылкой, чтобы получить бонусные дни Premium за приглашения.
        </p>
        <div className="field-row">
          <div className="status-pill">Код: {referral?.code ?? "—"}</div>
          {referral?.code && (
            <button
              type="button"
              className="button"
              onClick={() => handleCopy(referral.code)}
            >
              Скопировать код
            </button>
          )}
        </div>
        <div className="field-row" style={{ marginTop: "0.6rem" }}>
          <div className="notice" style={{ flex: 1 }}>
            {referral?.link ?? "Ссылка появится после генерации кода."}
          </div>
          {referral?.link && (
            <button
              type="button"
              className="button"
              onClick={() => handleCopy(referral.link)}
            >
              Скопировать ссылку
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
