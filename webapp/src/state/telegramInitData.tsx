import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

const parseBoolean = (value: string | undefined): boolean =>
  value === "true" || value === "1";

const parseNumber = (value: string | undefined, fallback: number): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

export const telegramEnv = {
  diagnosticsEnabled: parseBoolean(import.meta.env.VITE_TG_DIAGNOSTICS),
  initDataRetry: parseNumber(import.meta.env.VITE_TG_INITDATA_RETRY, 10),
  initDataRetryDelayMs: parseNumber(
    import.meta.env.VITE_TG_INITDATA_RETRY_DELAY_MS,
    200,
  ),
  debugEnabled: parseBoolean(import.meta.env.VITE_TG_DEBUG),
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

type InitDataSource = "telegram" | "url-search" | "url-hash" | null;

const readInitDataFromUrl = (): { value: string; source: InitDataSource } => {
  if (typeof window === "undefined") {
    return { value: "", source: null };
  }
  const searchParams = new URLSearchParams(window.location.search);
  const searchValue = searchParams.get("tgWebAppData");
  if (searchValue) {
    return { value: searchValue, source: "url-search" };
  }
  const rawHash = window.location.hash.startsWith("#")
    ? window.location.hash.slice(1)
    : window.location.hash;
  const hash = rawHash.startsWith("?") ? rawHash.slice(1) : rawHash;
  const hashParams = new URLSearchParams(hash);
  const hashValue = hashParams.get("tgWebAppData");
  if (hashValue) {
    return { value: hashValue, source: "url-hash" };
  }
  return { value: "", source: null };
};

const readInitData = (): { value: string; source: InitDataSource } => {
  const telegramInitData = getTelegramWebApp()?.initData ?? "";
  if (telegramInitData) {
    return { value: telegramInitData, source: "telegram" };
  }
  return readInitDataFromUrl();
};

let currentInitData = "";
let currentInitDataSource: InitDataSource = null;

export const getCurrentInitData = (): string => currentInitData;
export const getCurrentInitDataSource = (): InitDataSource => currentInitDataSource;

const setCurrentInitData = (value: string, source: InitDataSource) => {
  currentInitData = value;
  currentInitDataSource = source;
};

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const retryInitData = async (
  retries: number,
  delayMs: number,
): Promise<{ value: string; source: InitDataSource }> => {
  let result = readInitData();
  if (result.value) {
    return result;
  }
  for (let attempt = 0; attempt < retries; attempt += 1) {
    await delay(delayMs);
    result = readInitData();
    if (result.value) {
      return result;
    }
  }
  return { value: "", source: null };
};

interface TelegramInitDataContextValue {
  initData: string;
  initDataLen: number;
  initDataSource: InitDataSource;
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
  const initialRead = readInitData();
  const initialInitData = getCurrentInitData() || initialRead.value;
  const initialSource = getCurrentInitDataSource() || initialRead.source;
  if (initialInitData && initialInitData !== currentInitData) {
    setCurrentInitData(initialInitData, initialSource);
  }
  const [initData, setInitData] = useState(() => initialInitData);
  const [initDataSource, setInitDataSource] = useState<InitDataSource>(initialSource);
  const [timestamp, setTimestamp] = useState(Date.now());
  const [isChecking, setIsChecking] = useState(false);
  const inflightRef = useRef<Promise<void> | null>(null);

  const refreshInitData = useCallback(async () => {
    if (inflightRef.current) {
      return inflightRef.current;
    }
    const task = (async () => {
      setIsChecking(true);
      if (telegramEnv.debugEnabled) {
        const hasTelegram = Boolean(getTelegramWebApp());
        console.info("[tg-init] start", { hasTelegram });
      }
      const data = await retryInitData(
        telegramEnv.initDataRetry,
        telegramEnv.initDataRetryDelayMs,
      );
      setCurrentInitData(data.value, data.source);
      setInitData(data.value);
      setInitDataSource(data.source);
      setTimestamp(Date.now());
      setIsChecking(false);
      if (telegramEnv.debugEnabled) {
        console.info("[tg-init] result", {
          initDataLen: data.value.length,
          source: data.source,
        });
      }
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
      initDataSource,
      isTelegram,
      platform,
      version,
      timestamp,
      isChecking,
      refreshInitData,
    }),
    [
      initData,
      initDataSource,
      isTelegram,
      platform,
      version,
      timestamp,
      isChecking,
      refreshInitData,
    ],
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
