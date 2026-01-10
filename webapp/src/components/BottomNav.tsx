import { NavLink } from "react-router-dom";

export const BottomNav = () => {
  return (
    <nav className="bottom-nav">
      <NavLink to="/" end>
        <span>🏠</span>
        <span>Главная</span>
      </NavLink>
      <NavLink to="/premium">
        <span>💎</span>
        <span>Premium</span>
      </NavLink>
      <NavLink to="/favorites">
        <span>⭐</span>
        <span>Избранное</span>
      </NavLink>
    </nav>
  );
};
