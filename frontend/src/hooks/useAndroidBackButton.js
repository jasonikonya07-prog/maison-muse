import { useEffect, useRef } from "react";
import { Capacitor } from "@capacitor/core";
import { App as CapacitorApp } from "@capacitor/app";

function useAndroidBackButton(onBackButton) {
  const handlerRef = useRef(onBackButton);

  useEffect(() => {
    handlerRef.current = onBackButton;
  }, [onBackButton]);

  useEffect(() => {
    if (Capacitor.getPlatform() !== "android") return undefined;

    let active = true;
    let listener;

    CapacitorApp.addListener("backButton", (event) => {
      handlerRef.current(event);
    }).then((handle) => {
      if (active) {
        listener = handle;
      } else {
        return handle.remove();
      }
    }).catch((error) => {
      console.error("Unable to register Android back button handler.", error);
    });

    return () => {
      active = false;
      if (listener) {
        void listener.remove().catch((error) => {
          console.error("Unable to remove Android back button handler.", error);
        });
      }
    };
  }, []);
}

export default useAndroidBackButton;
