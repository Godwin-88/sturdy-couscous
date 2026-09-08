import { useState, useCallback } from "react";

export type ToastType = "success" | "error" | "info";

export interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

let toastId = 0;
let addToast: ((toast: Omit<Toast, "id">) => void) | null = null;

export function showToast(message: string, type: ToastType = "info") {
  if (addToast) {
    addToast({ message, type });
  }
}

export function ToastContainer() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const handleAdd = useCallback((toast: Omit<Toast, "id">) => {
    const id = ++toastId;
    setToasts((prev) => [...prev, { ...toast, id }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  useState(() => {
    addToast = handleAdd;
    return () => {
      addToast = null;
    };
  });

  if (toasts.length === 0) return null;

  return (
    <div className="toast-container" aria-live="polite" aria-atomic="false">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast ${toast.type}`} role="status">
          {toast.type === "success" && "✓ "}
          {toast.type === "error" && "✕ "}
          {toast.type === "info" && "ℹ "}
          {toast.message}
        </div>
      ))}
    </div>
  );
}
