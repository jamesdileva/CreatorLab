import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { createSeries, endSeries, listSeries } from "../services/story";
import { listCreators } from "../services/creators";
import type { Creator } from "../types/creator";
import type { Series } from "../types/story";

export default function SeriesList() {
  const [series, setSeries] = useState<Series[] | null>(null);
  const [creators, setCreators] = useState<Creator[]>([]);
  const [error, setError] = useState("");
  const [creatorId, setCreatorId] = useState("");
  const [name, setName] = useState("");

  const refresh = (filterCreator?: number) => {
    listSeries(filterCreator)
      .then(setSeries)
      .catch((e) => setError(e instanceof Error ? e.message : "load failed"));
  };

  useEffect(() => {
    listCreators(false)
      .then(setCreators)
      .catch(() => undefined);
    refresh();
  }, []);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createSeries(name, Number(creatorId));
      setName("");
      refresh();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "create failed");
    }
  };

  if (series === null) return <main style={{ padding: 24 }}>loading series…</main>;

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 760 }}>
      <p>
        <Link to="/dashboard">← Dashboard</Link>
      </p>
      <h1>Series (Sprint 2.1)</h1>
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      {series.length === 0 ? (
        <p>No series yet.</p>
      ) : (
        <ul>
          {series.map((s) => (
            <li key={s.id}>
              <Link to={`/series/${s.id}`}>
                {s.name} ({s.status})
              </Link>
              <br />
              <small>creator id {s.creator_id}</small>
            </li>
          ))}
        </ul>
      )}

      <h2>New series</h2>
      <form onSubmit={(e) => void onCreate(e)}>
        <select
          value={creatorId}
          onChange={(e) => setCreatorId(e.target.value)}
          required
        >
          <option value="">select creator…</option>
          {creators.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>{" "}
        <input
          placeholder="series name (e.g. Hank's World)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />{" "}
        <button type="submit">create</button>
      </form>
    </main>
  );
}
