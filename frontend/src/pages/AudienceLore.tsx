import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { distillLore, listLore, promoteLore } from "../services/story";
import type { LoreEntry } from "../services/story";

export default function AudienceLore() {
  const [lore, setLore] = useState<LoreEntry[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = () =>
    listLore()
      .then(setLore)
      .catch(() => setLore([]));

  useEffect(() => {
    void refresh();
  }, []);

  const onDistill = async () => {
    setBusy(true);
    try {
      setLore(await distillLore());
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "distill failed");
    } finally {
      setBusy(false);
    }
  };

  const onPromote = async (id: number) => {
    try {
      await promoteLore(id);
      refresh();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "promote failed");
    }
  };

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 860 }}>
      <p>
        <Link to="/dashboard">← Dashboard</Link>
      </p>
      <h1>Audience lore (Sprint 14.2)</h1>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      <p style={{ fontSize: 12, color: "#555" }}>
        Themes the simulated audience keeps watching across episodes. Promoting a
        recurring theme writes it into the series canon as a running joke — the
        audience starts contributing to the fictional universe.
      </p>
      <button disabled={busy} onClick={() => void onDistill()}>
        {busy ? "distilling…" : "distill from simulation runs"}
      </button>

      {lore.length === 0 ? (
        <p>no themes yet — run simulations, then distill</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>theme</th>
              <th>creator</th>
              <th>episodes</th>
              <th>avg watch</th>
              <th>status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {lore.map((l) => (
              <tr key={l.id}>
                <td>{l.theme}</td>
                <td>{l.creator_id}</td>
                <td>{l.episode_ids.join(", ")}</td>
                <td>{(l.avg_watch * 100).toFixed(1)}%</td>
                <td>
                  {l.status}
                  {l.promoted_canon_id ? ` (canon #${l.promoted_canon_id})` : ""}
                </td>
                <td>
                  {l.status === "recurring" && (
                    <button onClick={() => void onPromote(l.id)}>promote</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
