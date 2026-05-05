import { useEffect, useRef, useState, useCallback } from "react";
import { io, Socket } from "socket.io-client";


// Types

export interface PriceData {
  symbol: string;
  price: number;
  prev_price?: number;
  change: number;
  pct_change: number;
  timestamp: string;
  asset_class: string;
  name: string;
  localTimestamp?: Date;
  direction?: "up" | "down" | "unchanged";
}

// REST fallback data type
interface MarketData {
  spx: number | null;
  vix: number | null;
  tenYear: number | null;
  twoYear: number | null;
  dxy: number | null;
  eurusd: number | null;
  gold: number | null;
  oil: number | null;
  fed: number | null;
}

export interface RegimeChangeData {
  regime: string;
  timestamp: string;
  details?: {
    confidence?: number;
    [key: string]: any;
  };
}

export interface MarketStreamState {
  isConnected: boolean;
  prices: Record<string, PriceData>;
  regimeChange: RegimeChangeData | null;
  lastUpdate: Date | null;
  error: string | null;
  socket: Socket | null;
  getPrice: (symbol: string) => PriceData | null;
  getAllPrices: () => PriceData[];
  restFallback?: MarketData | null;
}


// SINGLETON: shared socket instance across all components

let _sharedSocket: Socket | null = null;
let _connectionCount = 0;
let _socketErrorLogged = false;
let _socketRetryCount = 0;

// Connect directly to backend — bypass Vite proxy for WebSocket
const BACKEND_URL = import.meta.env.VITE_API_URL || "http://localhost:3002";

export function useMarketStream(): MarketStreamState {
  const [isConnected, setIsConnected] = useState(false);
  const [prices, setPrices] = useState<Record<string, PriceData>>({});
  const [regimeChange, setRegimeChange] = useState<RegimeChangeData | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);
  const localUpdateRef = useRef<Record<string, PriceData>>({});

  useEffect(() => {
    // Create socket singleton on first mount
    if (!_sharedSocket) {
      _sharedSocket = io(BACKEND_URL, {
        path: "/socket.io",
        transports: ["websocket", "polling"],
        reconnection: true,
        reconnectionDelay: 3000,
        reconnectionDelayMax: 15000,
        reconnectionAttempts: 5,
        timeout: 10000,
        withCredentials: false,
      });
    }

    const socket = _sharedSocket;
    _connectionCount++;

    // ─────────────────────────────────────────────────────────────────────────
    // Event Handlers
    // ─────────────────────────────────────────────────────────────────────────

    const handleConnect = () => {
      _socketRetryCount = 0;
      _socketErrorLogged = false;
      setIsConnected(true);
      setError(null);
    };

    const handleDisconnect = () => {
      setIsConnected(false);
    };

    // Stop retrying after max attempts to prevent flood
    socket.io.on("reconnect_failed", () => {
      socket.disconnect();
    });

    const handleLiveData = (data: { prices: PriceData[] }) => {
      if (data?.prices) {
        const updates: Record<string, PriceData> = {};
        const now = new Date();

        data.prices.forEach((item) => {
          const prevPrice = localUpdateRef.current[item.symbol]?.price;
          let direction: "up" | "down" | "unchanged" = "unchanged";
          if (prevPrice !== undefined) {
            direction = item.price > prevPrice ? "up" : item.price < prevPrice ? "down" : "unchanged";
          }

          updates[item.symbol] = {
            ...item,
            localTimestamp: now,
            direction,
          };
        });

        localUpdateRef.current = { ...localUpdateRef.current, ...updates };
        setPrices((prev) => ({ ...prev, ...updates }));
        setLastUpdate(now);
      }
    };

    const handleRegimeChange = (data: RegimeChangeData) => {
      setRegimeChange(data);
      // Auto-dismiss after 10 seconds
      setTimeout(() => setRegimeChange(null), 10000);
    };

    const handleConnectError = (err: Error) => {
      _socketRetryCount++;
      if (!_socketErrorLogged) {
        _socketErrorLogged = true;
      }
      setError(err.message);
      setIsConnected(false);
    };

    // ─────────────────────────────────────────────────────────────────────────
    // Attach listeners
    // ─────────────────────────────────────────────────────────────────────────

    socket.on("connect", handleConnect);
    socket.on("disconnect", handleDisconnect);
    socket.on("live_data", handleLiveData);
    socket.on("REGIME_CHANGE", handleRegimeChange);
    socket.on("connect_error", handleConnectError);

    // Set initial connected state
    if (socket.connected) {
      setIsConnected(true);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Cleanup on unmount
    // ─────────────────────────────────────────────────────────────────────────

    return () => {
      _connectionCount--;
      socket.off("connect", handleConnect);
      socket.off("disconnect", handleDisconnect);
      socket.off("live_data", handleLiveData);
      socket.off("REGIME_CHANGE", handleRegimeChange);
      socket.off("connect_error", handleConnectError);

      // CRITICAL FIX: Don't disconnect in React StrictMode - let socket persist
      // This prevents rapid connect/disconnect cycles
      if (_connectionCount <= 0) {
        _connectionCount = 0;
        // Keep socket connected - don't null it out
      }
    };
  }, []);

  const getPrice = useCallback(
    (symbol: string): PriceData | null => {
      return prices[symbol] || null;
    },
    [prices]
  );

  const getAllPrices = useCallback((): PriceData[] => {
    return Object.values(prices);
  }, [prices]);

  // REST fallback — poll dashboard when WebSocket is not delivering data
  const [restData, setRestData] = useState<MarketData | null>(null);
  const hasLiveData = isConnected && Object.keys(prices).length > 0;

  useEffect(() => {
    if (hasLiveData) return; // Don't poll if we have live data

    const poll = async () => {
      try {
        const res = await fetch('/api/dashboard');
        if (!res.ok) return;
        const json = await res.json();
        const km = json?.keyMetrics;
        const ri = json?.riskIndicators;
        if (!km) return;

        // FIXED: Map all ticker fields from dashboard response (BUG 9)
        setRestData({
          spx: km.spxLevel ?? km.growth?.value ?? null,
          vix: ri?.vix ?? km.risk?.value ?? null,
          tenYear: km.tenYearYield ?? km.liquidity?.value ?? null,
          twoYear: km.twoYearYield ?? null,
          dxy: km.dxy ?? null,
          eurusd: km.eurusd ?? null,
          gold: km.gold ?? null,
          oil: km.oil ?? null,
          fed: km.fedRate ?? null,
        });
      } catch {}
    };

    poll();
    const id = setInterval(poll, 30000);
    return () => clearInterval(id);
  }, [hasLiveData]);

  return {
    isConnected: isConnected || !!restData,
    prices: hasLiveData ? prices : (restData as unknown as Record<string, PriceData>) || {},
    getPrice,
    getAllPrices: hasLiveData ? getAllPrices : () => [],
    regimeChange,
    lastUpdate: hasLiveData ? lastUpdate : (restData ? new Date() : null),
    error,
    socket: _sharedSocket,
    restFallback: restData,
  };
}

export default useMarketStream;
