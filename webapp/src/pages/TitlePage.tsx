import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Episode, TitleDetail, WatchRequestPayload } from "../api/types";
import { WatchStatus } from "../components/WatchStatus";
import { useUserData } from "../state/userData";
import { useWatchFlow } from "../state/watchFlow";

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
        setAudioId(data.available_audio_ids[0] ?? null);
        setQualityId(data.available_quality_ids[0] ?? null);
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
    const payload: WatchRequestPayload = {
      title_id: title.id,
      episode_id: title.type === "series" ? selectedEpisodeId : null,
      audio_id: audioId,
      quality_id: qualityId,
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
        <button className="button secondary" onClick={() => navigate(-1)}>
          ← Назад
        </button>
        {title.type === "series" && (
          <>
            <button className="button secondary" onClick={() => goEpisode("prev")}>
              ◀ Серия
            </button>
            <button className="button secondary" onClick={() => goEpisode("next")}>
              Серия ▶
            </button>
          </>
        )}
      </div>

      <div className="card poster-hero">
        <img src={title.poster_url || "/placeholder-poster.svg"} alt={title.name} />
        <div>
          <h2 className="section-title">{title.name}</h2>
          <div className="meta">{title.year || "—"}</div>
          <p className="meta">{title.description || "Описание пока пустое."}</p>
          <div className="inline-actions">
            <button className="icon-button" onClick={() => toggleFavorite(title.id)}>
              {favoriteIds.has(title.id) ? "⭐" : "☆"} Избранное
            </button>
            <button className="icon-button" onClick={() => toggleSubscription(title.id)}>
              {subscriptions.has(title.id) ? "🔔" : "🔕"} Подписка
            </button>
          </div>
        </div>
      </div>

      {title.type === "series" && (
        <div className="card">
          <h3 className="section-title">Сезоны и серии</h3>
          <div className="field-row">
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
          </div>
        </div>
      )}

      <div className="card">
        <h3 className="section-title">Озвучка и качество</h3>
        <div className="field-row">
          <select
            value={audioId ?? ""}
            onChange={(event) => setAudioId(Number(event.target.value))}
          >
            {title.available_audio_ids.map((idValue) => (
              <option key={idValue} value={idValue}>
                Озвучка {idValue}
              </option>
            ))}
          </select>
          <select
            value={qualityId ?? ""}
            onChange={(event) => setQualityId(Number(event.target.value))}
          >
            {title.available_quality_ids.map((idValue) => (
              <option key={idValue} value={idValue}>
                Качество {idValue}
              </option>
            ))}
          </select>
        </div>
        <button className="button" onClick={handleWatch}>
          {title.type === "series" ? "Смотреть серию" : "Смотреть"}
        </button>
      </div>

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
