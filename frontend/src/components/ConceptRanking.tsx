import { useEffect, useState } from "react";
import {
  getConceptComparison,
  recordHumanRanking,
  scoreConceptSet,
} from "../services/story";
import type {
  Concept,
  ConceptComparison,
  ScoreSetResult,
} from "../services/story";

const DIMS = [
  "hook",
  "character_fit",
  "novelty",
  "story_potential",
  "audience_relevance",
  "episode_continuity",
];

export default function ConceptRanking({ concepts }: { concepts: Concept[] }) {
  const [result, setResult] = useState<ScoreSetResult | null>(null);
  const [order, setOrder] = useState<number[]>([]);
  const [comparison, setComparison] = useState<ConceptComparison | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setResult(null);
    setOrder([]);
    setComparison(null);
  }, [concepts.map((c) => c.id).join(",")]);

  const setId = concepts[0]?.set_id;

  const onScore = async () => {
    setBusy(true);
    try {
      const r = await scoreConceptSet(setId);
      setResult(r);
      setOrder(r.ranked.map((item) => item.concept.id));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "scoring failed");
    } finally {
      setBusy(false);
    }
  };

  const onSaveRanking = async () => {
    setBusy(true);
    try {
      await recordHumanRanking(setId, order, "recorded from dashboard");
      const c = await getConceptComparison(setId);
      setComparison(c);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "ranking failed");
    } finally {
      setBusy(false);
    }
  };

  const move = (index: number, delta: number) => {
    const next = [...order];
    const target = index + delta;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    setOrder(next);
  };

  const titleOf = (id: number) => concepts.find((c) => c.id === id)?.title ?? `#${id}`;

  if (!setId) return null;

  return (
    <div style={{ marginTop: 12 }}>
      <button disabled={busy} onClick={() => void onScore()}>
        {busy ? "working…" : "score concepts"}
      </button>
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      {result && (
        <div style={{ marginTop: 8 }}>
          <h4>System ranking ({result.scorer_version})</h4>
          <ol>
            {result.ranked.map((item) => (
              <li key={item.concept.id}>
                <strong>{item.concept.title}</strong> — composite{" "}
                {item.composite.toFixed(3)}
                <div style={{ fontSize: 12, color: "#444" }}>
                  {DIMS.map((d) => (
                    <span key={d} style={{ marginRight: 10 }}>
                      {d.replace("_", " ")}: {item.scores[d]?.toFixed(2)}
                    </span>
                  ))}
                </div>
              </li>
            ))}
          </ol>

          <h4>Your ranking (drag-free editor)</h4>
          <ol>
            {order.map((id, i) => (
              <li key={id}>
                {titleOf(id)}{" "}
                <button onClick={() => move(i, -1)} disabled={i === 0}>
                  ↑
                </button>{" "}
                <button onClick={() => move(i, 1)} disabled={i === order.length - 1}>
                  ↓
                </button>
              </li>
            ))}
          </ol>
          <button disabled={busy} onClick={() => void onSaveRanking()}>
            save ranking & compare
          </button>
        </div>
      )}

      {comparison && (
        <div
          style={{
            border: "1px solid #ccc",
            borderRadius: 8,
            padding: 12,
            marginTop: 8,
          }}
        >
          <h4>Sim vs your judgment</h4>
          <p>
            Spearman: {comparison.correlation.spearman} · Kendall τ:{" "}
            {comparison.correlation.kendall_tau}
          </p>
          <p>
            top-1 match: {String(comparison.agreement.top_1_match)} · top-3 overlap:{" "}
            {comparison.agreement.top_3_overlap} · directional accuracy:{" "}
            {comparison.agreement.directional_accuracy} (n={comparison.sample_size})
          </p>
        </div>
      )}
    </div>
  );
}
