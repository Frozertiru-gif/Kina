import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { Title, TitleType } from "../api/types";
import { TitleCard } from "../components/TitleCard";
import { useUserData } from "../state/userData";

export const HomePage = () => {
  const [tab, setTab] = useState<TitleType>("movie");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Title[]>([]);
  const [topTitles, setTopTitles] = useState<Title[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { favorites, favoriteIds, refreshFavorites, toggleFavorite } = useUserData();

  useEffect(() => {
    refreshFavorites().catch(() => null);
  }, [refreshFavorites]);

  useEffect(() => {
    const loadTop = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await api.getTop(tab);
        setTopTitles(data);
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setLoading(false);
      }
    };
    if (!searchQuery) {
      loadTop();
    }
  }, [tab, searchQuery]);

  const handleSearch = async () => {
    if (!searchQuery) {
      setSearchResults([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await api.search(searchQuery, tab);
      setSearchResults(data);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const visibleTitles = useMemo(() => {
    if (searchQuery) {
      return searchResults;
    }
    return topTitles;
  }, [searchQuery, searchResults, topTitles]);

  return (
    <div className="main-content">
      <div className="search-bar">
        <input
          placeholder="Поиск фильмов и сериалов"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
        />
        <button className="button secondary" onClick={handleSearch}>
          Найти
        </button>
      </div>

      <div className="card">
        <div className="tab-row">
          <button
            className={`tab ${tab === "movie" ? "active" : ""}`}
            onClick={() => setTab("movie")}
          >
            Movies
          </button>
          <button
            className={`tab ${tab === "series" ? "active" : ""}`}
            onClick={() => setTab("series")}
          >
            Series
          </button>
        </div>
        <h2 className="section-title">
          {searchQuery ? "Результаты поиска" : "Топ недели"}
        </h2>
        {loading && <div className="notice">Загружаем каталог...</div>}
        {error && <div className="notice">Ошибка: {error}</div>}
        {!loading && !visibleTitles.length && (
          <div className="notice">Ничего не найдено.</div>
        )}
        <div className="title-grid">
          {visibleTitles.map((title) => (
            <TitleCard
              key={title.id}
              title={title}
              isFavorite={favoriteIds.has(title.id)}
              onToggleFavorite={() => toggleFavorite(title.id)}
            />
          ))}
        </div>
      </div>

      <div className="card">
        <h2 className="section-title">Избранное</h2>
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
      </div>
    </div>
  );
};
