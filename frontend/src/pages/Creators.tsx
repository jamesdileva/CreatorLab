import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  createCreator,
  deactivateCreator,
  listCreators,
} from "../services/creators";
import type { Creator } from "../types/creator";

export default function Creators() {
  const [creators, setCreators] = useState<Creator[]>([]);
  const [showInactive, setShowInactive] = useState(false);
  const [error, setError] = useState("");
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
