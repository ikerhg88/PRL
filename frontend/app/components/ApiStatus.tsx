"use client";

import { useEffect, useState } from "react";

type HealthState = "checking" | "online" | "offline";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8001";

export function ApiStatus() {
  const [state, setState] = useState<HealthState>("checking");

  useEffect(() => {
    let cancelled = false;
    fetch(`${apiBaseUrl}/api/v1/health`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`API returned ${response.status}`);
        }
        if (!cancelled) {
          setState("online");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState("offline");
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return <span className={`apiPill ${state}`}>API {state}</span>;
}
