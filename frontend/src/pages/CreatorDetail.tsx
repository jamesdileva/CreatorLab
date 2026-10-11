import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getCreator, updateCreator } from "../services/creators";
import type { Creator } from "../types/creator";

const csv = (xs: string[]) => xs.join(", ");
const uncsv = (s: string) =>
  s
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);

export default function CreatorDetail() {
  const { id } = useParams<{ id: string }>();
  const [creator, setCreator] = useState<Creator | null>(null);
  const [error, setError] = useState("");
  const [description, setDescription] = useState("");
  const [personality, setPersonality] = useState("");
  const [humor, setHumor] = useState("");
  const [interests, setInterests] = useState("");

  useEffect(() => {
    if (!id) return;
    getCreator(id)
      .then((c) => {
        setCreator(c);
        setDescription(c.description);
        setPersonality(c.personality);
        setHumor(c.humor_style);
        setInterests(csv(c.interests));
        setError("");
      })
      .catch((e) => setError(e instanceof Error ? e.message : "load failed"));
  }, [id]);

  const onSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!creator) return;
    try {
      const updated = await updateCreator(creator.id, {
        description,
        personality,
        humor_style: humor,
        interests: uncsv(interests),
      });
      setCreator(updated);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "save failed");
    }
  };

  const onToggleActive = async () => {
    if (!creator) return;
    try {
      setCreator(await updateCreator(creator.id, { active: !creator.active }));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "toggle failed");
    }
  };

  if (error && !creator) return <main style={{ padding: 24 }}>{error}</main>;
  if (!creator) return <main style={{ padding: 24 }}>loading…</main>;

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 720 }}>
      <p>
        <Link to="/creators">← Creators</Link>
      </p>
      <h1>
        {creator.name} ({creator.slug}){" "}
        {!creator.active && <em>[inactive]</em>}
      </h1>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      <p>
        <strong>Values:</strong> {csv(creator.values) || "—"}
      </p>
      <p>
        <strong>Goals:</strong> {csv(creator.goals) || "—"}
      </p>
      <p>
        <small>
          created {creator.created_at} · updated {creator.updated_at}
        </small>
      </p>

      <form onSubmit={(e) => void onSave(e)}>
        <div>
          <label>
            description
            <br />
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              style={{ width: "100%" }}
            />
          </label>
        </div>
        <div>
          <label>
            personality
            <br />
            <textarea
              value={personality}
              onChange={(e) => setPersonality(e.target.value)}
              rows={3}
              style={{ width: "100%" }}
            />
          </label>
        </div>
        <div>
          <label>
            humor style
            <br />
            <input
              value={humor}
              onChange={(e) => setHumor(e.target.value)}
              style={{ width: "100%" }}
            />
          </label>
        </div>
        <div>
          <label>
            interests (comma-separated)
            <br />
            <input
              value={interests}
              onChange={(e) => setInterests(e.target.value)}
              style={{ width: "100%" }}
            />
          </label>
        </div>
        <button type="submit">save</button>{" "}
        <button type="button" onClick={() => void onToggleActive()}>
          {creator.active ? "deactivate" : "reactivate"}
        </button>
      </form>
    </main>
  );
}
