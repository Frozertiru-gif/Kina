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

  const { favoriteIds, refreshFavorites, toggleFavorite } = useUserData();
  const normalizedQuery = searchQuery.trim();
  const isSearching = normalizedQuery.length > 0;

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
    if (!isSearching) {
      loadTop();
    }
  }, [tab, isSearching]);

  const handleSearch = async () => {
    if (!normalizedQuery) {
      setSearchResults([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await api.search(normalizedQuery, tab);
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
      <section className="hero-card">
        <div>
          <span className="status-pill">Kina · Telegram WebApp</span>
          <h2 className="hero-title">Смотри кино и сериалы без лишних шагов</h2>
          <p className="meta">
            Ищи новинки, добавляй в избранное и запускай просмотр прямо в чате.
          </p>
        </div>
      </section>

      <section className="search-panel">
        <div className="search-input">
          <input
            placeholder="Поиск фильмов и сериалов"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                handleSearch();
              }
            }}
          />
          {searchQuery && (
            <button
              className="icon-button ghost"
              type="button"
              onClick={() => {
                setSearchQuery("");
                setSearchResults([]);
                setError(null);
              }}
            >
              ✕
            </button>
          )}
        </div>
        <button className="button" onClick={handleSearch}>
          Найти
        </button>
      </section>

      <section className="card">
        <div className="tab-row">
          <button
            className={`tab ${tab === "movie" ? "active" : ""}`}
            onClick={() => setTab("movie")}
          >
            Фильмы
          </button>
          <button
            className={`tab ${tab === "series" ? "active" : ""}`}
            onClick={() => setTab("series")}
          >
            Сериалы
          </button>
        </div>
        <h2 className="section-title">
          {isSearching ? "Результаты поиска" : "Популярное"}
        </h2>
        <p className="meta">
          {isSearching
            ? `По запросу “${normalizedQuery}”`
            : "Собрали топовые тайтлы за неделю."}
        </p>
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
      </section>

    </div>
  );
};
