export type AuthStatus = "pending" | "ready" | "missing" | "failed";

type Deferred = {
  promise: Promise<void>;
  resolve: () => void;
};

const createDeferred = (): Deferred => {
  let resolve: () => void = () => undefined;
  const promise = new Promise<void>((res) => {
    resolve = res;
  });
  return { promise, resolve };
};

let authStatus: AuthStatus = "pending";
let deferred = createDeferred();

export const resetAuthGate = () => {
  authStatus = "pending";
  deferred = createDeferred();
};

export const markAuthReady = () => {
  authStatus = "ready";
  deferred.resolve();
};

export const markAuthMissing = () => {
  authStatus = "missing";
  deferred.resolve();
};

export const markAuthFailed = () => {
  authStatus = "failed";
  deferred.resolve();
};

export const getAuthStatus = () => authStatus;

export const waitForAuthReady = async () => {
  if (authStatus === "ready") {
    return;
  }
  if (authStatus === "missing") {
    throw new Error("auth_missing");
  }
  if (authStatus === "failed") {
    throw new Error("auth_failed");
  }
  await deferred.promise;
  if (authStatus !== "ready") {
    throw new Error(authStatus === "missing" ? "auth_missing" : "auth_failed");
  }
};
