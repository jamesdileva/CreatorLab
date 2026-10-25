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
        <Link to="/series">Series</Link>{" · "}
        <Link to="/simulation">Simulation</Link>{" · "}
        <Link to="/simulation-scale">Scale study</Link>{" · "}
        <Link to="/checkpoint">Research checkpoint</Link>{" · "}
        <Link to="/review">Review queue</Link>{" · "}
        <Link to="/youtube">YouTube</Link>{" · "}
        <Link to="/analytics">Analytics</Link>{" · "}
        <Link to="/experiments">Experiments</Link>{" · "}
        <Link to="/reality-gap">Reality gap</Link>{" · "}
        <Link to="/universe">Universe</Link>{" · "}
        <Link to="/lore">Audience lore</Link>{" · "}
        <Link to="/competition">Competition</Link>{" · "}
        <Link to="/emulator">Emulator</Link>
      </nav>
      <p>Episodes, simulation, and reality-gap land in later sprints.</p>
    </main>
  );
}
