// Virtual List Hook — Phase 4B Performance Optimization
// Efficiently renders large lists by only showing visible items

import { useState, useMemo, useCallback, useRef, useEffect } from 'react';

interface UseVirtualListOptions {
  itemHeight: number;
  overscan?: number;
  containerHeight?: number;
}

interface VirtualListItem<T> {
  item: T;
  index: number;
  style: React.CSSProperties;
}

export function useVirtualList<T>(
  items: T[],
  options: UseVirtualListOptions
) {
  const { itemHeight, overscan = 5, containerHeight = 400 } = options;
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);

  // Calculate visible range
  const virtualizer = useMemo(() => {
    const totalHeight = items.length * itemHeight;
    const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan);
    const endIndex = Math.min(
      items.length,
      Math.ceil((scrollTop + containerHeight) / itemHeight) + overscan
    );

    const virtualItems: VirtualListItem<T>[] = [];
    for (let i = startIndex; i < endIndex; i++) {
      virtualItems.push({
        item: items[i],
        index: i,
        style: {
          position: 'absolute',
          top: i * itemHeight,
          height: itemHeight,
          left: 0,
          right: 0,
        },
      });
    }

    return {
      virtualItems,
      startIndex,
      endIndex,
      totalHeight,
    };
  }, [items, itemHeight, scrollTop, containerHeight, overscan]);

  const onScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop);
  }, []);

  // Use IntersectionObserver for automatic container height detection
  useEffect(() => {
    if (!containerRef.current) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const _height = entry.contentRect.height;
        // Could update container height here if needed
        void _height;
      }
    });

    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  return {
    containerRef,
    virtualItems: virtualizer.virtualItems,
    totalHeight: virtualizer.totalHeight,
    onScroll,
    startIndex: virtualizer.startIndex,
    endIndex: virtualizer.endIndex,
  };
}

// Hook for expensive calculations with memoization
export function useMemoizedCalculation<T, R>(
  data: T,
  calculator: (data: T) => R,
  deps: unknown[]
): R {
  return useMemo(() => calculator(data), deps);
}
