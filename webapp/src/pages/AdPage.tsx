import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { WatchStatus } from "../components/WatchStatus";
import { useWatchFlow } from "../state/watchFlow";

const AD_TIMER_SECONDS = 10;

export const AdPage = () => {
  const navigate = useNavigate();
  const { state, dispatch } = useWatchFlow();
  const [nonce, setNonce] = useState<string | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(AD_TIMER_SECONDS);
  const [cooldownMessage, setCooldownMessage] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);

  const canContinue = secondsLeft <= 0 && !!nonce && !completed && !cooldownMessage;

  useEffect(() => {
    const startAds = async () => {
      if (!state.variantId) {
        navigate("/");
        return;
      }
      try {
        const response = await api.adsStart(state.variantId);
        setNonce(response.nonce);
        setSecondsLeft(AD_TIMER_SECONDS);
      } catch (err) {
        const message = (err as Error).message;
        if (message === "ad_cooldown") {
          const retryAfter =
            err instanceof ApiError && typeof err.data?.retry_after === "number"
              ? err.data.retry_after
              : null;
          const suffix = retryAfter ? ` через ${retryAfter} сек` : " позже";
          setCooldownMessage(`Реклама уже недавно была, попробуй${suffix}.`);
          dispatch({ type: "ads_cooldown", message });
        } else {
          dispatch({ type: "error", message });
        }
      }
    };
    startAds().catch(() => null);
  }, [dispatch, navigate, state.variantId]);

  useEffect(() => {
    if (!nonce || cooldownMessage) {
      return undefined;
    }
    if (secondsLeft <= 0) {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      setSecondsLeft((prev) => prev - 1);
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [secondsLeft, nonce, cooldownMessage]);

  const handleContinue = async () => {
    if (!nonce || !state.params || !state.variantId) {
      return;
    }
    try {
      await api.adsComplete(nonce);
      dispatch({ type: "request_start" });
      const watchResponse = await api.watchRequest(state.params);
      dispatch({ type: "dispatching", variantId: watchResponse.variant_id });
      await api.watchDispatch(watchResponse.variant_id);
      dispatch({ type: "queued", variantId: watchResponse.variant_id });
      setCompleted(true);
    } catch (err) {
      dispatch({ type: "error", message: (err as Error).message });
    }
  };

  const timerLabel = useMemo(() => {
    if (cooldownMessage) {
      return "⛔";
    }
    return secondsLeft > 0 ? `${secondsLeft}` : "✓";
  }, [secondsLeft, cooldownMessage]);

  return (
    <div className="main-content">
      <div className="card ad-screen">
        <span className="status-pill">Ads gate</span>
        <h2 className="section-title">Реклама идёт...</h2>
        <div className="timer">{timerLabel}</div>
        <p className="meta">
          Подождите несколько секунд, чтобы продолжить просмотр. Мы поддерживаем контент без
          подписки.
        </p>
        {cooldownMessage ? (
          <>
            <div className="notice">{cooldownMessage}</div>
            <button className="button secondary" onClick={() => navigate(-1)}>
              Назад
            </button>
          </>
        ) : (
          <button className="button" disabled={!canContinue} onClick={handleContinue}>
            Продолжить
          </button>
        )}
      </div>

      {state.status === "queued" && completed && (
        <WatchStatus
          title="Готово!"
          description="Видео отправлено ботом в личные сообщения."
          showBotLink
        />
      )}
      {state.status === "error" && state.message && (
        <div className="notice">Ошибка: {state.message}</div>
      )}
    </div>
  );
};
