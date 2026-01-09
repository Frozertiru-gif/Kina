import { NavLink } from "react-router-dom";

export const BottomNav = () => {
  return (
    <nav className="bottom-nav">
      <NavLink to="/" end>
        <span>🏠</span>
        <span>Home</span>
      </NavLink>
      <NavLink to="/premium">
        <span>💎</span>
        <span>Premium</span>
      </NavLink>
      <NavLink to="/profile">
        <span>👤</span>
        <span>Profile</span>
      </NavLink>
    </nav>
  );
};
