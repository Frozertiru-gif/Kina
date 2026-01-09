import React, { createContext, useContext, useReducer } from "react";
import type { WatchRequestPayload } from "../api/types";

export type WatchStatus =
  | "idle"
  | "requesting"
  | "ad_gate"
  | "dispatching"
  | "queued"
  | "error"
  | "ads_cooldown";

export interface WatchState {
  status: WatchStatus;
  params: WatchRequestPayload | null;
  variantId: number | null;
  message?: string;
}

type WatchAction =
  | { type: "set_params"; payload: WatchRequestPayload }
  | { type: "request_start" }
  | { type: "ad_gate"; variantId: number }
  | { type: "dispatching"; variantId: number }
  | { type: "queued"; variantId: number }
  | { type: "error"; message: string }
  | { type: "ads_cooldown"; message: string }
  | { type: "reset" };

const initialState: WatchState = {
  status: "idle",
  params: null,
  variantId: null,
};

const reducer = (state: WatchState, action: WatchAction): WatchState => {
  switch (action.type) {
    case "set_params":
      return { ...state, params: action.payload };
    case "request_start":
      return { ...state, status: "requesting", message: undefined };
    case "ad_gate":
      return { ...state, status: "ad_gate", variantId: action.variantId };
    case "dispatching":
      return { ...state, status: "dispatching", variantId: action.variantId };
    case "queued":
      return { ...state, status: "queued", variantId: action.variantId };
    case "error":
      return { ...state, status: "error", message: action.message };
    case "ads_cooldown":
      return { ...state, status: "ads_cooldown", message: action.message };
    case "reset":
      return initialState;
    default:
      return state;
  }
};

const WatchContext = createContext<
  | {
      state: WatchState;
      dispatch: React.Dispatch<WatchAction>;
    }
  | undefined
>(undefined);

export const WatchProvider = ({ children }: { children: React.ReactNode }) => {
  const [state, dispatch] = useReducer(reducer, initialState);
  return (
    <WatchContext.Provider value={{ state, dispatch }}>
      {children}
    </WatchContext.Provider>
  );
};

export const useWatchFlow = () => {
  const context = useContext(WatchContext);
  if (!context) {
    throw new Error("useWatchFlow must be used within WatchProvider");
  }
  return context;
};
