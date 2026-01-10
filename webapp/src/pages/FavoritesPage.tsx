import { useEffect } from "react";
import { TitleCard } from "../components/TitleCard";
import { useUserData } from "../state/userData";

export const FavoritesPage = () => {
  const { favorites, favoriteIds, refreshFavorites, toggleFavorite } = useUserData();

  useEffect(() => {
    refreshFavorites().catch(() => null);
  }, [refreshFavorites]);

  return (
    <div className="main-content">
      <section className="card">
        <h2 className="section-title">Избранное</h2>
        <p className="meta">Тайтлы, которые ты отметил звёздочкой.</p>
        {favorites.length === 0 && <div className="notice">Пока пусто.</div>}
        <div className="title-grid">
          {favorites.map((title) => (
            <TitleCard
              key={title.id}
              title={title}
              isFavorite={favoriteIds.has(title.id)}
              onToggleFavorite={() => toggleFavorite(title.id)}
            />
          ))}
        </div>
      </section>
    </div>
  );
};
