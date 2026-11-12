import "@ds/tokens.css";
import "@ds/components/bundle.css";
import "./app.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";

const media = matchMedia("(prefers-color-scheme: light)");
const applyTheme = () => {
  document.documentElement.dataset.theme = media.matches ? "light" : "dark";
};
applyTheme();
media.addEventListener("change", applyTheme);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
