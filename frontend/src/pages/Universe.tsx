import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { createUniverseEntity, deleteUniverseEntity, listUniverse } from "../services/story";

const KINDS = ["LOCATION", "CHARACTER", "EVENT", "OBJECT", "RELATIONSHIP", "TIMELINE"];

export default function Universe() {
  const [entities, setEntities] = useState<Awaited<ReturnType<typeof listUniverse>>>([]);
  const [kind, setKind] = useState("LOCATION");
  const [name, setName] = useState("");
  const [statement, setStatement] = useState("");
  const [error, setError] = useState("");

  const refresh = () =>
    listUniverse()
      .then(setEntities)
      .catch((e) => setError(e instanceof Error ? e.message : "load failed"));

  useEffect(() => {
    void refresh();
  }, []);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createUniverseEntity({ kind, name, statement });
      setName("");
      setStatement("");
      refresh();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "create failed");
    }
  };

  const onDelete = async (id: number) => {
    try {
      await deleteUniverseEntity(id);
      refresh();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "delete failed");
    }
  };

  const grouped = KINDS.map((k) => ({
    kind: k,
    items: entities.filter((e) => e.kind === k),
  })).filter((group) => group.items.length > 0);

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 800 }}>
      <p>
        <Link to="/dashboard">← Dashboard</Link>
      </p>
      <h1>Universe canon (Sprint 14.1)</h1>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      <p style={{ fontSize: 12, color: "#555" }}>
        Shared-world facts obeyed by every channel's episode generation —
        episodes across creators stay consistent.
      </p>

      {grouped.length === 0 ? (
        <p>no universe facts yet</p>
      ) : (
        grouped.map((group) => (
          <div key={group.kind}>
            <h3>{group.kind}</h3>
            <ul>
              {group.items.map((e) => (
                <li key={e.id}>
                  <strong>{e.name}</strong> — {e.statement}{" "}
                  <button onClick={() => void onDelete(e.id)}>delete</button>
                </li>
              ))}
            </ul>
          </div>
        ))
      )}

      <h2>New universe fact</h2>
      <form onSubmit={(e) => void onCreate(e)}>
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>{" "}
        <input
          placeholder="name (e.g. The County Fair)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />{" "}
        <input
          placeholder="statement"
          value={statement}
          onChange={(e) => setStatement(e.target.value)}
          style={{ width: "45%" }}
          required
        />{" "}
        <button type="submit">add</button>
      </form>
    </main>
  );
}
