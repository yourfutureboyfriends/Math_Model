// Real-time WebSocket Hook — Phase 4C
// Manages WebSocket connection for live price updates

import { useEffect, useRef, useCallback, useState } from 'react';
import { useMacroStore } from '@/store/macroStore';

interface WebSocketMessage {
  type: 'price' | 'regime' | 'signal' | 'ping' | 'error';
  data?: unknown;
  timestamp?: string;
}

interface UseRealtimeOptions {
  onPriceUpdate?: (prices: Record<string, number>) => void;
  onRegimeChange?: (regime: unknown) => void;
  onSignalUpdate?: (signals: unknown) => void;
  onError?: (error: Error) => void;
  reconnectDelay?: number;
  maxReconnects?: number;
}

export function useRealtime(options: UseRealtimeOptions = {}) {
  const {
    onPriceUpdate,
    onRegimeChange,
    onSignalUpdate,
    onError,
    reconnectDelay = 5000,
    maxReconnects = 5,
  } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCountRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const store = useMacroStore();

  const connect = useCallback(() => {
    try {
      // Close existing connection
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }

      const wsUrl = `ws://${window.location.host}/ws/prices`;
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('[WebSocket] Connected');
        setIsConnected(true);
        reconnectCountRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          setLastMessage(message);

          switch (message.type) {
            case 'price':
              if (onPriceUpdate && message.data) {
                onPriceUpdate(message.data as Record<string, number>);
              }
              // Update store directly
              if (message.data && typeof message.data === 'object') {
                const prices = message.data as Record<string, number>;
                Object.entries(prices).forEach(([symbol, price]) => {
                  // Update store if method exists
                  if (store.prices && symbol in store.prices) {
                    (store.prices as unknown as Record<string, number | null>)[symbol] = price;
                  }
                });
              }
              break;
            case 'regime':
              if (onRegimeChange) {
                onRegimeChange(message.data);
              }
              break;
            case 'signal':
              if (onSignalUpdate) {
                onSignalUpdate(message.data);
              }
              break;
            case 'error':
              if (onError) {
                onError(new Error('WebSocket error message received'));
              }
              break;
            case 'ping':
              // Send pong response
              ws.send(JSON.stringify({ type: 'pong' }));
              break;
          }
        } catch (e) {
          console.error('[WebSocket] Message parse error:', e);
        }
      };

      ws.onclose = () => {
        console.log('[WebSocket] Disconnected');
        setIsConnected(false);

        // Auto-reconnect
        if (reconnectCountRef.current < maxReconnects) {
          reconnectCountRef.current += 1;
          console.log(`[WebSocket] Reconnecting in ${reconnectDelay}ms (attempt ${reconnectCountRef.current})`);
          reconnectTimeoutRef.current = setTimeout(connect, reconnectDelay);
        }
      };

      ws.onerror = (error) => {
        console.error('[WebSocket] Error:', error);
        if (onError) {
          onError(new Error('WebSocket connection error'));
        }
      };

      wsRef.current = ws;
    } catch (e) {
      console.error('[WebSocket] Setup error:', e);
      if (onError) {
        onError(e instanceof Error ? e : new Error('WebSocket setup failed'));
      }
    }
  }, [onPriceUpdate, onRegimeChange, onSignalUpdate, onError, reconnectDelay, maxReconnects]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setIsConnected(false);
  }, []);

  const send = useCallback((message: WebSocketMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
      return true;
    }
    return false;
  }, []);

  useEffect(() => {
    connect();

    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  return {
    isConnected,
    lastMessage,
    connect,
    disconnect,
    send,
  };
}

// Hook for price subscriptions only
export function usePriceSubscription(symbols: string[]) {
  const [prices, setPrices] = useState<Record<string, number>>({});

  const { isConnected, send } = useRealtime({
    onPriceUpdate: (newPrices) => {
      setPrices((prev) => ({ ...prev, ...newPrices }));
    },
  });

  // Subscribe to symbols when connected
  useEffect(() => {
    if (isConnected && symbols.length > 0) {
      send({
        type: 'price',
        data: { subscribe: symbols },
      });
    }
  }, [isConnected, symbols, send]);

  return { prices, isConnected };
}
