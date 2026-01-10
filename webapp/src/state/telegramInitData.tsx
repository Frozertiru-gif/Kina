import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

const parseBoolean = (value: string | undefined): boolean => value === "true";

const parseNumber = (value: string | undefined, fallback: number): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

export const telegramEnv = {
  diagnosticsEnabled: parseBoolean(import.meta.env.VITE_TG_DIAGNOSTICS),
  initDataRetry: parseNumber(import.meta.env.VITE_TG_INITDATA_RETRY, 10),
  initDataRetryDelayMs: parseNumber(
    import.meta.env.VITE_TG_INITDATA_RETRY_DELAY_MS,
    100,
  ),
};

type TelegramWebApp = {
  initData?: string;
  platform?: string;
  version?: string;
};

const getTelegramWebApp = (): TelegramWebApp | undefined => {
  if (typeof window === "undefined") {
    return undefined;
  }
  return (window as typeof window & {
    Telegram?: { WebApp?: TelegramWebApp };
  }).Telegram?.WebApp;
};

const readInitData = (): string => getTelegramWebApp()?.initData ?? "";

let currentInitData = "";

export const getCurrentInitData = (): string => currentInitData;

const setCurrentInitData = (value: string) => {
  currentInitData = value;
};

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const retryInitData = async (retries: number, delayMs: number): Promise<string> => {
  let initData = readInitData();
  if (initData) {
    return initData;
  }
  for (let attempt = 0; attempt < retries; attempt += 1) {
    await delay(delayMs);
    initData = readInitData();
    if (initData) {
      return initData;
    }
  }
  return "";
};

interface TelegramInitDataContextValue {
  initData: string;
  initDataLen: number;
  isTelegram: boolean;
  platform: string | null;
  version: string | null;
  timestamp: number;
  isChecking: boolean;
  refreshInitData: () => Promise<void>;
}

const TelegramInitDataContext = createContext<TelegramInitDataContextValue | undefined>(
  undefined,
);

export const TelegramInitDataProvider = ({ children }: { children: React.ReactNode }) => {
  const initialInitData = getCurrentInitData() || readInitData();
  if (initialInitData && initialInitData !== currentInitData) {
    setCurrentInitData(initialInitData);
  }
  const [initData, setInitData] = useState(() => initialInitData);
  const [timestamp, setTimestamp] = useState(Date.now());
  const [isChecking, setIsChecking] = useState(false);
  const inflightRef = useRef<Promise<void> | null>(null);

  const refreshInitData = useCallback(async () => {
    if (inflightRef.current) {
      return inflightRef.current;
    }
    const task = (async () => {
      setIsChecking(true);
      const data = await retryInitData(
        telegramEnv.initDataRetry,
        telegramEnv.initDataRetryDelayMs,
      );
      setCurrentInitData(data);
      setInitData(data);
      setTimestamp(Date.now());
      setIsChecking(false);
    })().finally(() => {
      inflightRef.current = null;
    });
    inflightRef.current = task;
    return task;
  }, []);

  useEffect(() => {
    refreshInitData().catch(() => null);
  }, [refreshInitData]);

  const webApp = getTelegramWebApp();
  const isTelegram = Boolean(webApp);
  const platform = webApp?.platform ?? null;
  const version = webApp?.version ?? null;

  const value = useMemo(
    () => ({
      initData,
      initDataLen: initData.length,
      isTelegram,
      platform,
      version,
      timestamp,
      isChecking,
      refreshInitData,
    }),
    [initData, isTelegram, platform, version, timestamp, isChecking, refreshInitData],
  );

  return (
    <TelegramInitDataContext.Provider value={value}>
      {children}
    </TelegramInitDataContext.Provider>
  );
};

export const useTelegramInitData = () => {
  const context = useContext(TelegramInitDataContext);
  if (!context) {
    throw new Error("useTelegramInitData must be used within TelegramInitDataProvider");
  }
  return context;
};
