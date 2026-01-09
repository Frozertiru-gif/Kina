import { useUserData } from "../state/userData";

const plans = [
  { months: 1, label: "1 месяц", price: "149 ₽" },
  { months: 2, label: "2 месяца", price: "269 ₽" },
  { months: 3, label: "3 месяца", price: "379 ₽" },
  { months: 6, label: "6 месяцев", price: "649 ₽" },
];

export const PremiumPage = () => {
  const { premiumActive, premiumUntil } = useUserData();

  return (
    <div className="main-content">
      <div className="card">
        <h2 className="section-title">Premium доступ</h2>
        <div className="field-row">
          <div className="status-pill">
            {premiumActive ? "Premium активен" : "Premium не активен"}
          </div>
          {premiumUntil && (
            <div className="status-pill">
              До {new Date(premiumUntil).toLocaleString()}
            </div>
          )}
          {premiumActive && <div className="status-pill">Ads Disabled</div>}
        </div>
        <p className="meta">
          Оформите подписку, чтобы смотреть без рекламы и получать видео мгновенно.
        </p>
        <div className="premium-grid">
          {plans.map((plan) => (
            <div key={plan.months} className="premium-card">
              <strong>{plan.label}</strong>
              <span className="meta">{plan.price}</span>
              <button className="button">Выбрать</button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
