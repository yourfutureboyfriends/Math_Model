import { useEffect, useState, useCallback } from "react";
import { AlertTriangle, Calendar, Clock, TrendingUp } from "lucide-react";

interface CalendarEvent {
  id: number;
  event_name: string;
  importance: "HIGH" | "MEDIUM" | "LOW";
  release_datetime: string;
  actual?: string;
  forecast?: string;
  previous?: string;
  surprise_score?: number;
  affected_assets: string[];
}

interface CalendarData {
  upcoming: CalendarEvent[];
  this_week: CalendarEvent[];
  blackout_active: boolean;
  blackout_event: string | null;
  blackout_ends_at: string | null;
  minutes_to_next: number;
}

function formatCountdown(minutes: number): string {
  if (minutes < 0) return "Released";
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const mins = minutes % 60;
  if (days > 0) return `${days}d ${hours}h ${mins}m`;
  if (hours > 0) return `${hours}h ${mins}m`;
  return `${mins}m`;
}

function getImportanceColor(importance: string): string {
  switch (importance) {
    case "HIGH":
      return "border-l-4 border-amber-500 bg-amber-50/30";
    case "MEDIUM":
      return "border-l-4 border-amber-300 bg-amber-50/10";
    default:
      return "border-l-2 border-slate-200";
  }
}

function getSurpriseColor(score?: number): string {
  if (score === undefined || score === null) return "";
  if (score > 1.0) return "text-green-600 font-medium";
  if (score < -1.0) return "text-red-600 font-medium";
  return "text-slate-600";
}

export function EconomicCalendar() {
  const [data, setData] = useState<CalendarData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState<number>(0);

  const fetchCalendar = useCallback(async () => {
    try {
      const res = await fetch("/api/calendar");
      if (!res.ok) throw new Error("Failed to fetch calendar");
      const d = await res.json();
      setData(d);
      setCountdown(d.minutes_to_next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load calendar");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCalendar();
    const interval = setInterval(fetchCalendar, 60000); // Refresh every minute
    return () => clearInterval(interval);
  }, [fetchCalendar]);

  // Countdown timer for next event
  useEffect(() => {
    if (!data?.minutes_to_next) return;
    const timer = setInterval(() => {
      setCountdown((prev) => Math.max(0, prev - 1));
    }, 60000);
    return () => clearInterval(timer);
  }, [data?.minutes_to_next]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-500">Loading economic calendar...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
        <p className="text-red-600">{error}</p>
        <button
          onClick={fetchCalendar}
          className="mt-2 text-sm text-red-600 hover:text-red-700 underline"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data) return null;

  const nextHighImpact = data.upcoming.find((e) => e.importance === "HIGH");

  return (
    <div className="space-y-6">
      {/* This Week's Events */}
      {data.this_week.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-medium text-slate-700 flex items-center gap-2">
            <Calendar className="w-4 h-4" />
            This Week ({data.this_week.length} events)
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {data.this_week.slice(0, 4).map((event) => (
              <div
                key={event.id}
                className={`p-3 rounded-lg border ${getImportanceColor(
                  event.importance
                )}`}
              >
                <div className="text-xs text-slate-500 mb-1">
                  {/* FIXED (BUG 8): Use ISO date format */}
                  {new Date(event.release_datetime).toISOString().split('T')[0]}
                </div>
                <div className="font-medium text-slate-800 text-sm">
                  {event.event_name}
                </div>
                <div className="text-xs text-slate-500 mt-1">
                  {event.importance} impact
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Next HIGH Impact Countdown */}
      {nextHighImpact && (
        <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg">
          <div className="flex items-center gap-2 text-amber-800 mb-1">
            <Clock className="w-4 h-4" />
            <span className="font-medium">Next HIGH Impact Event</span>
          </div>
          <div className="text-2xl font-bold text-amber-900">
            {nextHighImpact.event_name}
          </div>
          <div className="text-amber-700">
            in {formatCountdown(countdown)}
          </div>
          <div className="text-sm text-amber-600 mt-1">
            Affected: {nextHighImpact.affected_assets?.join(", ") || "N/A"}
          </div>
        </div>
      )}

      {/* Full Calendar Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="text-left py-2 px-3 font-medium text-slate-600">
                Event
              </th>
              <th className="text-left py-2 px-3 font-medium text-slate-600">
                Date/Time
              </th>
              <th className="text-left py-2 px-3 font-medium text-slate-600">
                Forecast
              </th>
              <th className="text-left py-2 px-3 font-medium text-slate-600">
                Previous
              </th>
              <th className="text-left py-2 px-3 font-medium text-slate-600">
                Actual
              </th>
              <th className="text-left py-2 px-3 font-medium text-slate-600">
                Surprise
              </th>
            </tr>
          </thead>
          <tbody>
            {data.upcoming.map((event) => {
              const releaseDate = new Date(event.release_datetime);
              const isNext = event.id === data.upcoming[0]?.id;

              return (
                <tr
                  key={event.id}
                  className={`border-b border-slate-100 hover:bg-slate-50 ${
                    isNext ? "bg-amber-50/50" : ""
                  }`}
                >
                  <td className={`py-3 px-3 ${getImportanceColor(event.importance)}`}>
                    <div className="font-medium text-slate-800">
                      {event.event_name}
                    </div>
                    <div className="text-xs text-slate-500 flex items-center gap-1 mt-0.5">
                      <span
                        className={`inline-block w-2 h-2 rounded-full ${
                          event.importance === "HIGH"
                            ? "bg-amber-500"
                            : event.importance === "MEDIUM"
                            ? "bg-amber-300"
                            : "bg-slate-300"
                        }`}
                      />
                      {event.importance}
                    </div>
                  </td>
                  <td className="py-3 px-3">
                    <div className="text-slate-700">
                      {/* FIXED (BUG 8): Use ISO date format */}
                      {releaseDate.toISOString().split('T')[0]}
                    </div>
                    <div className="text-xs text-slate-500">
                      {releaseDate.toLocaleTimeString("en-US", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </div>
                  </td>
                  <td className="py-3 px-3 text-slate-600">
                    {event.forecast ?? "—"}
                  </td>
                  <td className="py-3 px-3 text-slate-600">
                    {event.previous ?? "—"}
                  </td>
                  <td className="py-3 px-3">
                    {event.actual ? (
                      <span className="font-medium text-slate-800">
                        {event.actual}
                      </span>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>
                  <td className="py-3 px-3">
                    {event.surprise_score !== null &&
                    event.surprise_score !== undefined ? (
                      <span
                        className={`inline-flex items-center gap-1 ${getSurpriseColor(
                          event.surprise_score
                        )}`}
                      >
                        <TrendingUp
                          className={`w-3 h-3 ${
                            event.surprise_score > 0
                              ? "text-green-600"
                              : "text-red-600 rotate-180"
                          }`}
                        />
                        {event.surprise_score > 0 ? "+" : ""}
                        {event.surprise_score.toFixed(2)}σ
                      </span>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {data.upcoming.length === 0 && (
        <div className="text-center py-8 text-slate-500">
          No upcoming economic events scheduled.
        </div>
      )}
    </div>
  );
}

// Blackout Banner Component - used in TerminalShell
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
      } catch (e) {
        // Silent fail
      }
    };

    checkBlackout();
    const interval = setInterval(checkBlackout, 60000);
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

export default EconomicCalendar;
