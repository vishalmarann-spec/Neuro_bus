import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./styles.css";

function App() {
  return (
    <main>
      <p className="eyebrow">NEURO_BUS / EVIDENCE INTELLIGENCE</p>
      <h1>Decisions with a visible chain of evidence.</h1>
      <p className="lede">
        The analyst workspace will be implemented after provenance, scoring, and API contracts
        pass their first end-to-end test.
      </p>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

