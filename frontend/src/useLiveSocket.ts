import { useEffect, useRef, useState } from "react";
import { wsUrl } from "./api";

export interface LiveEvent {
  type: string;
  [key: string]: any;
}

export function useLiveSocket(onEvent?: (e: LiveEvent) => void) {
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<LiveEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;
    let retryTimer: number;

    function connect() {
      const ws = new WebSocket(wsUrl());
      wsRef.current = ws;
      ws.onopen = () => !cancelled && setConnected(true);
      ws.onclose = () => {
        if (cancelled) return;
        setConnected(false);
        retryTimer = window.setTimeout(connect, 2000); // auto-reconnect, no manual refresh needed
      };
      ws.onmessage = (msg) => {
        const data = JSON.parse(msg.data) as LiveEvent;
        setLastEvent(data);
        onEvent?.(data);
      };
    }
    connect();

    return () => {
      cancelled = true;
      window.clearTimeout(retryTimer);
      wsRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { connected, lastEvent };
}
