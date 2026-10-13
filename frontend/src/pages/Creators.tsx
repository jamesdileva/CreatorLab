import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  createCreator,
  deactivateCreator,
  getStrategy,
  listCreators,
} from "../services/creators";
import type { Creator } from "../types/creator";
import type { CreatorStrategy } from "../services/creators";

export default function Creators() {
  const [creators, setCreators] = useState<Creator[]>([]);
  const [showInactive, setShowInactive] = useState(false);
  const [error, setError] = useState("");
  const [strategy, setStrategy] = useState<CreatorStrategy | null>(null);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");

  const refresh = async (includeInactive: boolean) => {
    try {
      setCreators(await listCreators(!includeInactive));
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load creators");
    }
  };

  useEffect(() => {
    void refresh(showInactive);
    getStrategy()
      .then(setStrategy)
      .catch(() => setStrategy(null));
  }, [showInactive]);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createCreator({ name, slug, description });
      setName("");
      setSlug("");
      setDescription("");
      await refresh(showInactive);
    } catch (err) {
      setError(err instanceof Error ? err.message : "create failed");
    }
  };

  const onDeactivate = async (id: number) => {
    try {
      await deactivateCreator(id);
      await refresh(showInactive);
    } catch (err) {
      setError(err instanceof Error ? err.message : "deactivate failed");
    }
  };

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 720 }}>
      <p>
        <Link to="/dashboard">← Dashboard</Link>
      </p>
      <h1>Creators</h1>
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      <label>
        <input
          type="checkbox"
          checked={showInactive}
          onChange={(e) => setShowInactive(e.target.checked)}
        />{" "}
        show inactive
      </label>

      <ul>
        {creators.map((c) => (
          <li key={c.id}>
            <Link to={`/creators/${c.id}`}>
              {c.name} ({c.slug})
            </Link>{" "}
            {!c.active && <em>[inactive]</em>}{" "}
            {c.active && (
              <button onClick={() => void onDeactivate(c.id)}>deactivate</button>
            )}
            <br />
            <small>{c.description}</small>
          </li>
        ))}
      </ul>

      <h2>Creator strategy (Sprint 10.2)</h2>
      {strategy ? (
        <div style={{ border: "1px solid #ccc", borderRadius: 8, padding: 12 }}>
          {!strategy.interpretation_allowed && (
            <p>
              need ≥2 creators with ≥{strategy.min_episodes} published episodes
              each ({strategy.sufficient_creators} ready) — no interpretation yet.
            </p>
          )}
          {Object.entries(strategy.per_creator).map(([slug, entry]) => (
            <div key={slug}>
              <h3>
                {entry.name} ({entry.episodes_with_metrics} episodes)
              </h3>
              <ul>
                {entry.observations.map((o, i) => (
                  <li key={i}>{o.text}</li>
                ))}
                {entry.observations.length === 0 && <li>no strong/weak signals yet</li>}
              </ul>
            </div>
          ))}
          <h3>Shared</h3>
          <ul>
            {strategy.shared.map((o, i) => (
              <li key={i}>{o.text}</li>
            ))}
            {strategy.shared.length === 0 && <li>no cross-creator patterns yet</li>}
          </ul>
        </div>
      ) : (
        <p>strategy unavailable</p>
      )}

      <h2>New creator</h2>
      <form onSubmit={(e) => void onCreate(e)}>
        <div>
          <input
            placeholder="name (e.g. Hank)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </div>
        <div>
          <input
            placeholder="slug (e.g. hank)"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            required
          />
        </div>
        <div>
          <input
            placeholder="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            style={{ width: "100%" }}
          />
        </div>
        <button type="submit">create</button>
      </form>
    </main>
  );
}
