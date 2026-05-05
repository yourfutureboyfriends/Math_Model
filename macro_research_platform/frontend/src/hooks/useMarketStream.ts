import { useEffect, useRef, useState, useCallback } from "react";
import { io, Socket } from "socket.io-client";

// ═══════════════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════════════
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
}

// ═══════════════════════════════════════════════════════════════════════════════
// SINGLETON: shared socket instance across all components
// ═══════════════════════════════════════════════════════════════════════════════
let _sharedSocket: Socket | null = null;
let _connectionCount = 0;

const SOCKET_URL = import.meta.env.VITE_SOCKET_URL || "http://localhost:8001";

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
      _sharedSocket = io(SOCKET_URL, {
        transports: ["websocket", "polling"], // Fallback for reliability
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionAttempts: 5,
      });
    }

    const socket = _sharedSocket;
    _connectionCount++;

    // ─────────────────────────────────────────────────────────────────────────
    // Event Handlers
    // ─────────────────────────────────────────────────────────────────────────

    const handleConnect = () => {
      console.log("[Socket] Connected:", socket.id);
      setIsConnected(true);
      setError(null);
    };

    const handleDisconnect = (reason: string) => {
      console.log("[Socket] Disconnected:", reason);
      setIsConnected(false);
    };

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
      console.log("[Socket] Regime change:", data);
      setRegimeChange(data);
      // Auto-dismiss after 10 seconds
      setTimeout(() => setRegimeChange(null), 10000);
    };

    const handleConnectError = (err: Error) => {
      console.error("[Socket] Connection error:", err);
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

  return {
    isConnected,
    prices,
    getPrice,
    getAllPrices,
    regimeChange,
    lastUpdate,
    error,
    socket: _sharedSocket,
  };
}

export default useMarketStream;
