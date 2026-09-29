import React from "react";
import ReactDOM from "react-dom/client";
import "@fontsource-variable/dm-sans";
import "@fontsource/instrument-serif/latin-400.css";
import "@fontsource/instrument-serif/latin-400-italic.css";
import "leaflet/dist/leaflet.css";
import "./tokens.css";
import "./style.css";
import "./responsive.css";
import "./photo-controls.css";
import "./motion.css";
import "./effects.css";
import App from "./App";
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
