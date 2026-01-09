import { authInfo } from "../api/client";

interface WatchStatusProps {
  title: string;
  description: string;
  showBotLink?: boolean;
}

const getBotLink = () => {
  const envLink = import.meta.env.VITE_BOT_LINK as string | undefined;
  if (envLink) {
    return envLink;
  }
  return "https://t.me";
};

export const WatchStatus = ({ title, description, showBotLink = false }: WatchStatusProps) => {
  const openBotChat = () => {
    const link = getBotLink();
    const telegram = (window as typeof window & {
      Telegram?: { WebApp?: { openTelegramLink?: (url: string) => void } };
    }).Telegram?.WebApp;
    if (telegram?.openTelegramLink) {
      telegram.openTelegramLink(link);
    } else {
      window.open(link, "_blank", "noopener,noreferrer");
    }
  };

  return (
    <div className="card">
      <strong>{title}</strong>
      <div className="meta">{description}</div>
      {showBotLink && (
        <button className="button" onClick={openBotChat}>
          Открыть чат с ботом
        </button>
      )}
      {authInfo.devUserId && (
        <span className="status-pill">DEV {authInfo.devUserId}</span>
      )}
    </div>
  );
};
