import { authInfo } from "../api/client";

export const ProfilePage = () => {
  return (
    <div className="main-content">
      <div className="card">
        <h2 className="section-title">Профиль</h2>
        <div className="notice">
          Здесь будут настройки уведомлений, языка и подписки.
        </div>
        <div className="field-row">
          <div className="status-pill">InitData: {authInfo.initData ? "OK" : "—"}</div>
          {authInfo.devUserId && (
            <div className="status-pill">DEV ID: {authInfo.devUserId}</div>
          )}
        </div>
      </div>
    </div>
  );
};
