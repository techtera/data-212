"use client";

import { useEffect, useState } from "react";

const MOCK_ENABLED = process.env.NEXT_PUBLIC_USE_MOCK === "true";

export function MswStarter({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(!MOCK_ENABLED);

  useEffect(() => {
    if (!MOCK_ENABLED) return;
    let active = true;
    (async () => {
      try {
        const { worker } = await import("@/mocks/browser");
        await worker.start({
          onUnhandledRequest: "bypass",
          quiet: false,
          serviceWorker: { url: "/mockServiceWorker.js" },
        });
      } catch (err) {
        console.error("MSW start failed", err);
      } finally {
        if (active) setReady(true);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        starting mock backend...
      </div>
    );
  }
  return <>{children}</>;
}
