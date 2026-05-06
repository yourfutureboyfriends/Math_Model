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

// FIXED: Dynamic port from env (Fix 1)
const API_PORT = import.meta.env.VITE_API_PORT || '8000';
const API_HOST = import.meta.env.VITE_API_HOST || 'localhost';
const SOCKET_URL = import.meta.env.VITE_API_URL || `http://${API_HOST}:${API_PORT}`;

// Export for debugging
export const RESOLVED_SOCKET_URL = SOCKET_URL;

// SINGLETON: shared socket instance across all components
let _sharedSocket: Socket | null = null;
let _connectionCount = 0;
let _socketErrorLogged = false;
let _socketRetryCount = 0;

export function useMarketStream(): MarketStreamState {
  const [isConnected, setIsConnected] = useState(false);
  const [prices, setPrices] = useState<Record<string, PriceData>>({});
  const [regimeChange, setRegimeChange] = useState<RegimeChangeData | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);
  const localUpdateRef = useRef<Record<string, PriceData>>({});
  const fallbackTimerRef = useRef<NodeJS.Timeout | null>(null);
  const socketRef = useRef<Socket | null>(null);

  // REST fallback state
  const [restData, setRestData] = useState<MarketData | null>(null);
  const hasLiveData = isConnected && Object.keys(prices).length > 0;

  // REST fallback polling effect (Fix 1)
  useEffect(() => {
    // Poll every 15 seconds regardless as backup
    const poll = async () => {
      try {
        // Try dedicated market-stream endpoint first
        const res = await fetch('/api/market-stream');
        if (res.ok) {
          const data = await res.json();
          if (!data.error) {
            setRestData({
              spx: data.spx ?? null,
              vix: data.vix ?? null,
              tenYear: data.tenYear ?? null,
              twoYear: data.twoYear ?? null,
              dxy: data.dxy ?? null,
              eurusd: data.eurusd ?? null,
              gold: data.gld ?? null,
              oil: data.wti ?? null,
              fed: data.fed ?? null,
            });
            return;
          }
        }

        // Fallback to dashboard endpoint
        const dashRes = await fetch('/api/dashboard');
        if (!dashRes.ok) return;
        const json = await dashRes.json();
        const km = json?.keyMetrics;
        const ri = json?.riskIndicators;
        if (!km) return;

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

    // Initial poll after 3s delay (let WebSocket try first)
    const initialTimer = setTimeout(poll, 3000);
    // Then poll every 15 seconds
    const interval = setInterval(poll, 15000);

    return () => {
      clearTimeout(initialTimer);
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    // Create socket singleton on first mount
    if (!_sharedSocket) {
      // FIXED: Dynamic URL from env (Fix 1)
      _sharedSocket = io(SOCKET_URL, {
        path: "/socket.io",
        transports: ["websocket", "polling"],
        reconnection: true,
        reconnectionDelay: 2000,
        reconnectionDelayMax: 10000,
        reconnectionAttempts: 5,
        timeout: 10000,
        withCredentials: false,
      });
    }

    const socket = _sharedSocket;
    socketRef.current = socket;
    _connectionCount++;

    // Event Handlers
    const handleConnect = () => {
      _socketRetryCount = 0;
      _socketErrorLogged = false;
      setIsConnected(true);
      setError(null);
      // Clear fallback timer on successful connect
      if (fallbackTimerRef.current) {
        clearTimeout(fallbackTimerRef.current);
        fallbackTimerRef.current = null;
      }
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
      setTimeout(() => setRegimeChange(null), 10000);
    };

    const handleConnectError = (err: Error) => {
      _socketRetryCount++;
      if (!_socketErrorLogged) {
        _socketErrorLogged = true;
      }
      setError(err.message);
      setIsConnected(false);

      // FIXED: Start REST fallback after 3 failed retries (Fix 1)
      if (_socketRetryCount >= 3 && !fallbackTimerRef.current) {
        console.warn('[WebSocket] Falling back to REST polling');
      }
    };

    // Attach listeners
    socket.on("connect", handleConnect);
    socket.on("disconnect", handleDisconnect);
    socket.on("live_data", handleLiveData);
    socket.on("REGIME_CHANGE", handleRegimeChange);
    socket.on("connect_error", handleConnectError);

    // Set initial connected state
    if (socket.connected) {
      setIsConnected(true);
    }

    // Cleanup
    return () => {
      _connectionCount--;
      socket.off("connect", handleConnect);
      socket.off("disconnect", handleDisconnect);
      socket.off("live_data", handleLiveData);
      socket.off("REGIME_CHANGE", handleRegimeChange);
      socket.off("connect_error", handleConnectError);

      if (fallbackTimerRef.current) {
        clearTimeout(fallbackTimerRef.current);
        fallbackTimerRef.current = null;
      }

      if (_connectionCount <= 0) {
        _connectionCount = 0;
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
