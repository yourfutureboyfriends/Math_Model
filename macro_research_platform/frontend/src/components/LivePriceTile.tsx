import React, { useRef, useEffect, useState } from "react";
import { useMarketStream } from "@/hooks/useMarketStream";
import styles from "./LivePriceTile.module.css";


// Types

interface LivePriceTileProps {
  symbol: string;
  className?: string;
}

/**
 * LivePriceTile — Real-time price display with flash animation
 *
 * @param {string} symbol — The ticker symbol to display
 * @param {string} className — Additional CSS classes
 */
export function LivePriceTile({ symbol, className = "" }: LivePriceTileProps): React.ReactElement {
  const { getPrice, isConnected } = useMarketStream();
  const priceData = getPrice(symbol);
  const tileRef = useRef<HTMLDivElement>(null);
  const [flashClass, setFlashClass] = useState<string>("");
  const prevPriceRef = useRef<number | null>(null);

  // Flash animation effect when price changes
  useEffect(() => {
    if (!priceData?.price) return;

    const currentPrice = priceData.price;
    const prevPrice = prevPriceRef.current;

    if (prevPrice !== null && currentPrice !== prevPrice) {
      const direction = currentPrice > prevPrice ? styles["flash-up"] : styles["flash-down"];
      setFlashClass(direction);

      // Clear flash after animation
      const timer = setTimeout(() => {
        setFlashClass("");
      }, 500);

      return () => clearTimeout(timer);
    }

    prevPriceRef.current = currentPrice;
  }, [priceData?.price]);

  // Skeleton loading state
  if (!isConnected || !priceData) {
    return (
      <div className={`${styles["live-price-tile"]} ${styles["skeleton"]} ${className}`}>
        <div className={styles["tile-header"]}>
          <span className={`${styles["symbol"]} ${styles["shimmer"]}`}>{symbol}</span>
          <span className={`${styles["badge"]} ${styles["shimmer"]}`}>--</span>
        </div>
        <div className={`${styles["price"]} ${styles["shimmer"]}`}>--.--</div>
        <div className={`${styles["change"]} ${styles["shimmer"]}`}>--</div>
      </div>
    );
  }

  const { price, change, pct_change, name, asset_class } = priceData;
  const isPositive = change >= 0;
  const changeColor = isPositive ? styles["positive"] : styles["negative"];

  return (
    <div
      ref={tileRef}
      className={`${styles["live-price-tile"]} ${flashClass} ${className}`}
      data-asset-class={asset_class}
    >
      <div className={styles["tile-header"]}>
        <span className={styles["symbol"]} title={name}>
          {symbol.replace("^", "").replace("=X", "")}
        </span>
        <span className={`${styles["badge"]} ${changeColor}`}>
          {isPositive ? "▲" : "▼"}
        </span>
      </div>

      <div className={styles["price"]}>
        {price.toLocaleString("en-US", {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })}
      </div>

      <div className={`${styles["change"]} ${changeColor}`}>
        <span className={styles["change-value"]}>
          {isPositive ? "+" : ""}
          {change.toFixed(2)}
        </span>
        <span className={styles["change-pct"]}>
          ({isPositive ? "+" : ""}
          {pct_change.toFixed(2)}%)
        </span>
      </div>

      <div className={styles["meta"]}>
        <span className={styles["name"]}>{name}</span>
        <span className={styles["asset-class"]}>{asset_class}</span>
      </div>
    </div>
  );
}

export default LivePriceTile;
