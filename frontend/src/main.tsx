import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

// Theme bootstrap BEFORE first paint — avoids a flash of the wrong theme.
// Persisted choice (localStorage "ga-theme"); default = midnight blue (#030214).
try {
  if (localStorage.getItem("ga-theme") === "light") {
    document.documentElement.dataset.theme = "light";
  } else {
    delete document.documentElement.dataset.theme; // :root = midnight
  }
} catch {
  /* localStorage unavailable — midnight default applies */
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter
      future={{
        v7_startTransition: true,
        v7_relativeSplatPath: true,
      }}
    >
      <App />
    </BrowserRouter>
  </React.StrictMode>
);