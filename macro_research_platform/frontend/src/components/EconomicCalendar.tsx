// Blackout Banner — shown in TerminalShell when a high-impact economic event
// is imminent. Fetches /api/calendar/blackout every 60 seconds.

import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";

export function BlackoutBanner() {
  const [blackout, setBlackout] = useState<{
    active: boolean;
    event: string | null;
    minutes_remaining: number;
    affected_assets: string[];
  } | null>(null);

  useEffect(() => {
    const checkBlackout = async () => {
      try {
        const res = await fetch("/api/calendar/blackout");
        if (res.ok) {
          const data = await res.json();
          setBlackout(data);
        }
      } catch {
        // Silent fail — banner simply stays hidden
      }
    };

    checkBlackout();
    const interval = setInterval(checkBlackout, 60_000);
    return () => clearInterval(interval);
  }, []);

  if (!blackout?.active) return null;

  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-red border-b border-red px-4 py-2 shadow-lg">
      <div className="flex items-center justify-center gap-3">
        <AlertTriangle className="w-5 h-5 text-text-primary" />
        <span className="font-medium text-text-primary">
          ⚠ BLACKOUT ACTIVE: {blackout.event} in {blackout.minutes_remaining}m
        </span>
        <span className="text-text-secondary">
          | Affected: {blackout.affected_assets?.join(" ") || "N/A"}
        </span>
        <span className="text-text-tertiary font-medium">
          | Reduce new position sizing
        </span>
      </div>
    </div>
  );
}
