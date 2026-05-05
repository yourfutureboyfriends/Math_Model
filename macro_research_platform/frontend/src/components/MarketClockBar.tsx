import React, { useState, useEffect } from "react";
import styles from "./MarketClockBar.module.css";


// Types

interface MarketConfig {
  name: string;
  tz: string;
  open: string;
  close: string;
  city: string;
}

interface MarketStatus extends MarketConfig {
  status: "open" | "closed";
  localTime: string;
}

interface MarketStatusState {
  markets: MarketStatus[];
  timestamp: Date | null;
}

/**
 * MarketClockBar — Horizontal strip showing exchange open/closed status
 *
 * Displays major global exchanges with color-coded status indicators.
 * Uses pure timezone logic (no external API).
 */
export function MarketClockBar(): React.ReactElement {
  const [marketStatus, setMarketStatus] = useState<MarketStatusState>({
    markets: [],
    timestamp: null,
  });

  useEffect(() => {
    const updateMarketStatus = () => {
      const markets: MarketConfig[] = [
        {
          name: "NYSE",
          tz: "America/New_York",
          open: "09:30",
          close: "16:00",
          city: "NYC",
        },
        {
          name: "LSE",
          tz: "Europe/London",
          open: "08:00",
          close: "16:30",
          city: "LON",
        },
        {
          name: "Xetra",
          tz: "Europe/Berlin",
          open: "09:00",
          close: "17:30",
          city: "FRA",
        },
        {
          name: "TSE",
          tz: "Asia/Tokyo",
          open: "09:00",
          close: "15:00",
          city: "TKY",
        },
        {
          name: "HKEx",
          tz: "Asia/Hong_Kong",
          open: "09:30",
          close: "16:00",
          city: "HKG",
        },
        {
          name: "SGX",
          tz: "Asia/Singapore",
          open: "09:00",
          close: "17:00",
          city: "SGP",
        },
        {
          name: "ASX",
          tz: "Australia/Sydney",
          open: "10:00",
          close: "16:00",
          city: "SYD",
        },
      ];

      const now = new Date();

      const updatedMarkets: MarketStatus[] = markets.map((m) => {
        const localTime = now.toLocaleTimeString("en-US", {
          timeZone: m.tz,
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        });

        const localHour = parseInt(localTime.split(":")[0]);
        const localMinute = parseInt(localTime.split(":")[1]);
        const localTimeValue = localHour * 60 + localMinute;

        const [openHour, openMinute] = m.open.split(":").map(Number);
        const [closeHour, closeMinute] = m.close.split(":").map(Number);
        const openValue = openHour * 60 + openMinute;
        const closeValue = closeHour * 60 + closeMinute;

        // Check if weekend
        const localDateStr = now.toLocaleString("en-US", { timeZone: m.tz });
        const localDate = new Date(localDateStr);
        const isWeekday = localDate.getDay() > 0 && localDate.getDay() < 6;
        const isOpen =
          isWeekday && localTimeValue >= openValue && localTimeValue <= closeValue;

        return {
          ...m,
          status: isOpen ? "open" : "closed",
          localTime,
        };
      });

      setMarketStatus({
        markets: updatedMarkets,
        timestamp: now,
      });
    };

    updateMarketStatus();
    const interval = setInterval(updateMarketStatus, 60000); // Update every minute

    return () => clearInterval(interval);
  }, []);

  return (
    <div className={styles["market-clock-bar"]}>
      <div className={styles["market-list"]}>
        {marketStatus.markets.map((market) => (
          <div key={market.name} className={styles["market-item"]}>
            <span
              className={`${styles["market-dot"]} ${styles[market.status]}`}
              title={`${market.name}: ${market.status.toUpperCase()} (${market.localTime})`}
            />
            <span className={styles["market-label"]}>
              {market.city}
              <span className={styles["market-time"]}>{market.localTime}</span>
            </span>
          </div>
        ))}
      </div>

      {marketStatus.timestamp && (
        <div className={styles["market-timestamp"]}>
          Updated: {marketStatus.timestamp.toLocaleTimeString()}
        </div>
      )}
    </div>
  );
}

export default MarketClockBar;
