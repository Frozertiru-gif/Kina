import { telegramEnv, useTelegramInitData } from "../state/telegramInitData";

export const TelegramDiagnosticsBanner = () => {
  const { initData, initDataLen, isTelegram, platform, version, timestamp } =
    useTelegramInitData();

  if (!telegramEnv.diagnosticsEnabled) {
    return null;
  }

  const initDataPreview = initDataLen > 0 ? initData.slice(0, 40) : "empty";

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 1000,
        background: "rgba(10, 12, 18, 0.95)",
        color: "#f5f7fb",
        fontSize: "12px",
        lineHeight: 1.4,
        padding: "8px 12px",
        fontFamily: "Menlo, Monaco, Consolas, monospace",
      }}
    >
      <div>isTelegram: {String(isTelegram)}</div>
      <div>initDataLen: {initDataLen}</div>
      <div>initDataPreview: {initDataPreview}</div>
      <div>platform: {platform ?? "unknown"}</div>
      <div>version: {version ?? "unknown"}</div>
      <div>timestamp: {timestamp}</div>
    </div>
  );
};
