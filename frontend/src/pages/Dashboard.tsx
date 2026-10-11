import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

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
      <h1>CreatorLab — Dashboard (Sprint 1.1)</h1>
      <p>Backend health: {health}</p>
      <nav>
        <Link to="/creators">Creators</Link>{" · "}
        <Link to="/series">Series</Link>
      </nav>
      <p>Episodes, simulation, and reality-gap land in later sprints.</p>
    </main>
  );
}
