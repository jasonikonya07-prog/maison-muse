import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export const DEFAULT_FEATURES = Object.freeze({
  verifiedSellerBadge: true,
  agriFarmHub: true,
  liveSupportBot: true,
  whatsappDirectBypass: true,
});

const STORAGE_KEY = "mm-feature-flags";
const FeatureContext = createContext(null);

function readStoredFeatures() {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (!saved) return DEFAULT_FEATURES;
    const parsed = JSON.parse(saved);
    return Object.fromEntries(
      Object.keys(DEFAULT_FEATURES).map((key) => [
        key,
        typeof parsed?.[key] === "boolean" ? parsed[key] : DEFAULT_FEATURES[key],
      ]),
    );
  } catch (error) {
    console.error("Unable to read saved feature settings.", error);
    return DEFAULT_FEATURES;
  }
}

export function FeatureProvider({ children, initialFeatures }) {
  const [features, setFeatures] = useState(() => ({
    ...readStoredFeatures(),
    ...initialFeatures,
  }));

  const setFeature = useCallback((name, enabled) => {
    if (!Object.hasOwn(DEFAULT_FEATURES, name) || typeof enabled !== "boolean") {
      throw new TypeError("Choose a supported feature flag and a boolean value.");
    }
    setFeatures((current) => ({ ...current, [name]: enabled }));
  }, []);

  const resetFeatures = useCallback(() => setFeatures(DEFAULT_FEATURES), []);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(features));
    } catch (error) {
      console.error("Unable to save feature settings.", error);
    }
  }, [features]);

  useEffect(() => {
    const syncFeatures = (event) => {
      if (event.key === STORAGE_KEY) setFeatures(readStoredFeatures());
    };
    window.addEventListener("storage", syncFeatures);
    return () => window.removeEventListener("storage", syncFeatures);
  }, []);

  const value = useMemo(
    () => ({ ...features, features, setFeature, resetFeatures }),
    [features, resetFeatures, setFeature],
  );
  return <FeatureContext.Provider value={value}>{children}</FeatureContext.Provider>;
}

export function useFeatures() {
  const context = useContext(FeatureContext);
  if (!context) {
    throw new Error("useFeatures must be used within a FeatureProvider.");
  }
  return context;
}
