import React from "react";
import ReactDOM from "react-dom/client";
import "@fontsource-variable/dm-sans";
import "@fontsource/instrument-serif/latin-400.css";
import "@fontsource/instrument-serif/latin-400-italic.css";
import "../tokens.css";
import "./brand.css";
import Brand from "./Brand";
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Brand />
  </React.StrictMode>,
);
