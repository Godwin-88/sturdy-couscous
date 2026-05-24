import { useEffect, useRef, useState, useCallback } from "react";

export type WsStatus = "connecting" | "open" | "closed" | "error";

export function useWebSocket<T = unknown>(url: string, maxMessages = 300) {
  const wsRef    = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [messages, setMessages] = useState<T[]>([]);
  const [status,   setStatus]   = useState<WsStatus>("connecting");
  const [lastMsg,  setLastMsg]  = useState<T | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(url);
    wsRef.current = ws;
    setStatus("connecting");

    ws.onopen = () => {
      setStatus("open");
      if (retryRef.current) { clearTimeout(retryRef.current); retryRef.current = null; }
    };

    ws.onclose = () => {
      if (wsRef.current === ws) {
        setStatus("closed");
        retryRef.current = setTimeout(connect, 3000);
      }
    };

    ws.onerror = () => {
      if (wsRef.current === ws) ws.close();
    };

    ws.onmessage = (evt: MessageEvent<string>) => {
      let parsed: T;
      try   { parsed = JSON.parse(evt.data) as T; }
      catch { parsed = evt.data as unknown as T; }
      setLastMsg(parsed);
      setMessages(prev => [parsed, ...prev].slice(0, maxMessages));
    };
  }, [url, maxMessages]);

  useEffect(() => {
    connect();
    return () => {
      if (retryRef.current) { clearTimeout(retryRef.current); retryRef.current = null; }
      const ws = wsRef.current;
      wsRef.current = null;
      if (!ws) return;
      // Null handlers so callbacks don't fire after unmount
      ws.onclose   = null;
      ws.onerror   = null;
      ws.onmessage = null;
      if (ws.readyState === WebSocket.CONNECTING) {
        // Closing a CONNECTING socket logs a browser error; defer until open instead
        ws.onopen = () => ws.close();
      } else {
        ws.close();
      }
    };
  }, [connect]);

  return { messages, status, lastMsg };
}
