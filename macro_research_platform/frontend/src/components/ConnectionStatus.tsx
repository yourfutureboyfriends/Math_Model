import React from "react";
import { useMarketStream } from "@/hooks/useMarketStream";
import styles from "./ConnectionStatus.module.css";

/**
 * ConnectionStatus — Real-time connection indicator with pulsing dot
 *
 * Shows live connection status, ticker count, and last update time.
 */
export function ConnectionStatus(): React.ReactElement {
  const { isConnected, lastUpdate } = useMarketStream();

  const getStatusLabel = (): string => {
    if (isConnected) return "LIVE";
    return "OFFLINE";
  };

  const getStatusColor = (): string => {
    if (isConnected) return styles["status-live"];
    return styles["status-offline"];
  };

  const formatLastUpdate = (): string => {
    if (!lastUpdate) return "—";
    return lastUpdate.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  };

  return (
    <div className={`${styles["connection-status"]} ${getStatusColor()}`}>
      <div className={styles["status-indicator"]}>
        <span className={`${styles["pulse-dot"]} ${isConnected ? styles["pulsing"] : ""}`} />
        <span className={styles["status-label"]}>{getStatusLabel()}</span>
      </div>

      <div className={styles["status-details"]}>
        <span className={styles["ticker-count"]}>22 tickers</span>
        <span className={styles["separator"]}>|</span>
        <span className={styles["last-update"]}>{formatLastUpdate()}</span>
      </div>
    </div>
  );
}

export default ConnectionStatus;
