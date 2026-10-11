import { useEffect, useState } from "react";

export default function Dashboard() {
  const [health, setHealth] = useState<string>("checking…");

  useEffect(() => {
    fetch("http://localhost:8000/health")
      .then((r) => r.json())
      .then((j) => setHealth(j.status ?? "unknown"))
      .catch(() => setHealth("backend offline (expected until backend runs)"));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui", padding: 24 }}>
      <h1>CreatorLab — Dashboard (Sprint 0.1)</h1>
      <p>Backend health: {health}</p>
      <p>Creators, episodes, simulation, and reality-gap land in later sprints.</p>
    </main>
  );
}
