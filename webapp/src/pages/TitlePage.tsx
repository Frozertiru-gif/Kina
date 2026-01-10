import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { Episode, TitleDetail, WatchRequestPayload } from "../api/types";
import { WatchStatus } from "../components/WatchStatus";
import { useUserData } from "../state/userData";
import { useWatchFlow } from "../state/watchFlow";

const AUDIO_STORAGE_KEY = "kina:preferred_audio_id";
const QUALITY_STORAGE_KEY = "kina:preferred_quality_id";

const readStoredNumber = (key: string) => {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.localStorage.getItem(key);
  if (!raw) {
    return null;
  }
  const parsed = Number(raw);
  return Number.isNaN(parsed) ? null : parsed;
};

const persistNumber = (key: string, value: number | null) => {
  if (typeof window === "undefined") {
    return;
  }
  if (value === null) {
    window.localStorage.removeItem(key);
    return;
  }
  window.localStorage.setItem(key, String(value));
};

export const TitlePage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const titleId = Number(id);
  const [title, setTitle] = useState<TitleDetail | null>(null);
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [selectedSeason, setSelectedSeason] = useState(1);
  const [selectedEpisodeId, setSelectedEpisodeId] = useState<number | null>(null);
  const [audioId, setAudioId] = useState<number | null>(null);
  const [qualityId, setQualityId] = useState<number | null>(null);
  const [resolveStatus, setResolveStatus] = useState<"available" | "unavailable" | null>(
    null,
  );
  const [resolvedSelection, setResolvedSelection] = useState<{
    audioId: number;
    qualityId: number;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const { favoriteIds, subscriptions, toggleFavorite, toggleSubscription } = useUserData();
  const { state, dispatch } = useWatchFlow();

  useEffect(() => {
    const loadTitle = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await api.getTitle(titleId);
        setTitle(data);
        const storedAudio = readStoredNumber(AUDIO_STORAGE_KEY);
        const storedQuality = readStoredNumber(QUALITY_STORAGE_KEY);
        setAudioId(storedAudio ?? data.available_audio_ids[0] ?? null);
        setQualityId(storedQuality ?? data.available_quality_ids[0] ?? null);
        if (data.type === "series" && data.seasons.length) {
          setSelectedSeason(data.seasons[0].season_number);
        }
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setLoading(false);
      }
    };
    if (Number.isNaN(titleId)) {
      setError("Некорректный ID");
      setLoading(false);
      return;
    }
    loadTitle();
  }, [titleId]);

  const resolveSelection = async (nextAudioId: number | null, nextQualityId: number | null) => {
    if (!title) {
      return;
    }
    if (title.type === "series" && !selectedEpisodeId) {
      return;
    }
    try {
      const response = await api.watchResolve({
        title_id: title.id,
        episode_id: title.type === "series" ? selectedEpisodeId : null,
        audio_id: nextAudioId,
        quality_id: nextQualityId,
      });
      setResolveStatus("available");
      setResolvedSelection({ audioId: response.audio_id, qualityId: response.quality_id });
      setAudioId(response.audio_id);
      setQualityId(response.quality_id);
      persistNumber(AUDIO_STORAGE_KEY, response.audio_id);
      persistNumber(QUALITY_STORAGE_KEY, response.quality_id);
    } catch (err) {
      if (err instanceof ApiError && err.message === "variant_not_found") {
        setResolveStatus("unavailable");
        setResolvedSelection(null);
        return;
      }
      setResolveStatus(null);
    }
  };

  useEffect(() => {
    const loadEpisodes = async () => {
      if (!title || title.type !== "series") {
        setEpisodes([]);
        return;
      }
      const data = await api.getEpisodes(title.id, selectedSeason);
      setEpisodes(data);
      setSelectedEpisodeId(data[0]?.id ?? null);
    };
    loadEpisodes().catch(() => null);
  }, [title, selectedSeason]);

  useEffect(() => {
    if (!title) {
      return;
    }
    if (title.type === "series" && !selectedEpisodeId) {
      return;
    }
    if (!audioId && !qualityId) {
      return;
    }
    resolveSelection(audioId, qualityId).catch(() => null);
  }, [title, selectedEpisodeId]);

  const episodeIndex = useMemo(() => {
    if (!selectedEpisodeId) {
      return -1;
    }
    return episodes.findIndex((episode) => episode.id === selectedEpisodeId);
  }, [episodes, selectedEpisodeId]);

  const goEpisode = (direction: "prev" | "next") => {
    if (episodeIndex === -1) {
      return;
    }
    const targetIndex = direction === "prev" ? episodeIndex - 1 : episodeIndex + 1;
    if (targetIndex >= 0 && targetIndex < episodes.length) {
      setSelectedEpisodeId(episodes[targetIndex].id);
    }
  };

  const handleWatch = async () => {
    if (!title || !audioId || !qualityId) {
      return;
    }
    if (title.type === "series" && !selectedEpisodeId) {
      return;
    }
    let resolvedAudioId = resolvedSelection?.audioId ?? audioId;
    let resolvedQualityId = resolvedSelection?.qualityId ?? qualityId;
    try {
      const resolved = await api.watchResolve({
        title_id: title.id,
        episode_id: title.type === "series" ? selectedEpisodeId : null,
        audio_id: audioId,
        quality_id: qualityId,
      });
      resolvedAudioId = resolved.audio_id;
      resolvedQualityId = resolved.quality_id;
      setResolvedSelection({ audioId: resolvedAudioId, qualityId: resolvedQualityId });
      setResolveStatus("available");
    } catch (err) {
      if (err instanceof ApiError && err.message === "variant_not_found") {
        setResolveStatus("unavailable");
        dispatch({ type: "error", message: "Выбранный вариант недоступен." });
        return;
      }
      dispatch({ type: "error", message: "Не удалось проверить вариант." });
      return;
    }
    const payload: WatchRequestPayload = {
      title_id: title.id,
      episode_id: title.type === "series" ? selectedEpisodeId : null,
      audio_id: resolvedAudioId,
      quality_id: resolvedQualityId,
    };
    dispatch({ type: "set_params", payload });
    dispatch({ type: "request_start" });
    try {
      const response = await api.watchRequest(payload);
      if (response.mode === "direct") {
        dispatch({ type: "dispatching", variantId: response.variant_id });
        await api.watchDispatch(response.variant_id);
        dispatch({ type: "queued", variantId: response.variant_id });
      } else {
        dispatch({ type: "ad_gate", variantId: response.variant_id });
        navigate("/ad");
      }
    } catch (err) {
      dispatch({ type: "error", message: (err as Error).message });
    }
  };

  if (loading) {
    return (
      <div className="main-content">
        <div className="notice">Загружаем карточку...</div>
      </div>
    );
  }

  if (error || !title) {
    return (
      <div className="main-content">
        <div className="notice">Ошибка: {error || "нет данных"}</div>
      </div>
    );
  }

  return (
    <div className="main-content">
      <div className="inline-actions">
        <button className="button ghost" onClick={() => navigate(-1)}>
          ← Назад
        </button>
      </div>

      <section className="card title-hero">
        <img src={title.poster_url || "/placeholder-poster.svg"} alt={title.name} />
        <div className="title-hero__content">
          <div className="title-hero__meta">
            <span className="status-pill">{title.type === "movie" ? "Фильм" : "Сериал"}</span>
            <span className="status-pill">{title.year || "—"}</span>
          </div>
          <h2 className="section-title title-hero__title">{title.name}</h2>
          <p className="meta">{title.description || "Описание пока пустое."}</p>
          <div className="inline-actions">
            <button className="icon-button" onClick={() => toggleFavorite(title.id)}>
              {favoriteIds.has(title.id) ? "⭐ В избранном" : "☆ В избранное"}
            </button>
            {title.type === "series" && (
              <button className="icon-button" onClick={() => toggleSubscription(title.id)}>
                {subscriptions.has(title.id) ? "🔔 Подписка активна" : "🔕 Подписаться"}
              </button>
            )}
          </div>
        </div>
      </section>

      {title.type === "series" && (
        <section className="card">
          <div className="section-header">
            <h3 className="section-title">Сезоны и серии</h3>
            <div className="inline-actions">
              <button className="button ghost" onClick={() => goEpisode("prev")}>
                ◀ Пред.
              </button>
              <button className="button ghost" onClick={() => goEpisode("next")}>
                След. ▶
              </button>
            </div>
          </div>
          <div className="field-row">
            <label className="field">
              <span className="field-label">Сезон</span>
              <select
                value={selectedSeason}
                onChange={(event) => setSelectedSeason(Number(event.target.value))}
              >
                {title.seasons.map((season) => (
                  <option key={season.id} value={season.season_number}>
                    Сезон {season.season_number} ({season.episodes_count})
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-label">Серия</span>
              <select
                value={selectedEpisodeId ?? ""}
                onChange={(event) => setSelectedEpisodeId(Number(event.target.value))}
              >
                {episodes.map((episode) => (
                  <option key={episode.id} value={episode.id}>
                    Серия {episode.episode_number} {episode.name ? `· ${episode.name}` : ""}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </section>
      )}

      <section className="card">
        <h3 className="section-title">Озвучка и качество</h3>
        <div className="field-row">
          <label className="field">
            <span className="field-label">Озвучка</span>
            <select
              value={audioId ?? ""}
              onChange={(event) => {
                const nextAudioId = Number(event.target.value);
                setAudioId(nextAudioId);
                persistNumber(AUDIO_STORAGE_KEY, nextAudioId);
                resolveSelection(nextAudioId, qualityId).catch(() => null);
              }}
            >
              {title.available_audio_ids.map((idValue) => (
                <option key={idValue} value={idValue}>
                  Озвучка {idValue}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Качество</span>
            <select
              value={qualityId ?? ""}
              onChange={(event) => {
                const nextQualityId = Number(event.target.value);
                setQualityId(nextQualityId);
                persistNumber(QUALITY_STORAGE_KEY, nextQualityId);
                resolveSelection(audioId, nextQualityId).catch(() => null);
              }}
            >
              {title.available_quality_ids.map((idValue) => (
                <option key={idValue} value={idValue}>
                  Качество {idValue}
                </option>
              ))}
            </select>
          </label>
        </div>
        {resolveStatus && (
          <div className="status-pill">
            {resolveStatus === "available" ? "Вариант доступен" : "Вариант недоступен"}
          </div>
        )}
        <button className="button" onClick={handleWatch}>
          {title.type === "series" ? "Смотреть серию" : "Смотреть"}
        </button>
      </section>

      {state.status === "dispatching" && (
        <WatchStatus
          title="Отправляем видео в Telegram..."
          description="Сейчас бот отправит файл в личные сообщения."
          showBotLink
        />
      )}
      {state.status === "queued" && (
        <WatchStatus
          title="Готово!"
          description="Видео отправлено ботом. Проверьте личные сообщения."
          showBotLink
        />
      )}
      {state.status === "error" && state.message && (
        <div className="notice">Ошибка: {state.message}</div>
      )}
    </div>
  );
};
