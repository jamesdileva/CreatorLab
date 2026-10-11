import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  createMemory,
  deleteMemory,
  generateCreatorVoice,
  getCreator,
  getIdentity,
  listMemories,
  updateCreator,
  updateIdentity,
} from "../services/creators";
import { MEMORY_TYPES } from "../types/creator";
import type { CharacterIdentity } from "../services/creators";
import type { Creator, CreatorMemory, CreatorVoice } from "../types/creator";

const env = import.meta.env as Record<string, string | undefined>;
const API_ROOT = env.VITE_API_URL ?? "http://localhost:8000";

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
  const [voiceMessage, setVoiceMessage] = useState(
    "What do you think about automated tractors?"
  );
  const [voice, setVoice] = useState<CreatorVoice | null>(null);
  const [voiceError, setVoiceError] = useState("");
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [memories, setMemories] = useState<CreatorMemory[] | null>(null);
  const [memType, setMemType] = useState<string>("CANON");
  const [memContent, setMemContent] = useState("");
  const [memImportance, setMemImportance] = useState("0.5");
  const [identity, setIdentity] = useState<CharacterIdentity | null>(null);

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

  const refreshMemories = async (creatorId: number) => {
    listMemories(creatorId)
      .then(setMemories)
      .catch(() => setMemories([]));
    getIdentity(String(creatorId))
      .then(setIdentity)
      .catch(() => setIdentity(null));
  };

  useEffect(() => {
    if (!id) return;
    void refreshMemories(Number(id));
  }, [id]);

  const onCreateMemory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!creator) return;
    createMemory(creator.id, {
      type: memType,
      content: memContent,
      importance: Number(memImportance),
    })
      .then(() => {
        setMemContent("");
        void refreshMemories(creator.id);
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "memory create failed")
      );
  };

  const onDeleteMemory = (memoryId: number) => {
    if (!creator) return;
    deleteMemory(creator.id, memoryId)
      .then(() => void refreshMemories(creator.id))
      .catch((err) =>
        setError(err instanceof Error ? err.message : "memory delete failed")
      );
  };

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

  const onTestVoice = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!creator) return;
    setVoiceBusy(true);
    setVoiceError("");
    try {
      setVoice(await generateCreatorVoice(creator.id, voiceMessage));
    } catch (err) {
      setVoice(null);
      setVoiceError(err instanceof Error ? err.message : "generate failed");
    } finally {
      setVoiceBusy(false);
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

      <h2>Test voice (Sprint 1.2)</h2>
      <form onSubmit={(e) => void onTestVoice(e)}>
        <label>
          give the creator a prompt
          <br />
          <textarea
            value={voiceMessage}
            onChange={(e) => setVoiceMessage(e.target.value)}
            rows={2}
            style={{ width: "100%" }}
          />
        </label>
        <br />
        <button type="submit" disabled={voiceBusy}>
          {voiceBusy ? "generating…" : "generate response"}
        </button>
      </form>
      {voiceError && <p style={{ color: "crimson" }}>{voiceError}</p>}
      {voice && (
        <div
          style={{
            border: "1px solid #ccc",
            borderRadius: 8,
            padding: 12,
            marginTop: 8,
          }}
        >
          <p style={{ whiteSpace: "pre-wrap" }}>{voice.text}</p>
          <small>
            provider: {voice.provider} · model: {voice.model} · prompt:{" "}
            {voice.prompt_version}
          </small>
          {voice.memories_used.length > 0 && (
            <>
              <br />
              <small>
                memories used: {voice.memories_used.length} (see panel below)
              </small>
            </>
          )}
        </div>
      )}

      <h2>Memory (Sprint 1.3)</h2>
      {memories === null ? (
        <p>loading memories…</p>
      ) : (
        <ul>
          {memories.map((m) => (
            <li key={m.id}>
              <strong>{m.type}</strong> · importance {m.importance.toFixed(2)}
              <br />
              {m.content}{" "}
              <button onClick={() => onDeleteMemory(m.id)}>delete</button>
            </li>
          ))}
          {memories.length === 0 && <li>(no memories stored yet)</li>}
        </ul>
      )}
      <form onSubmit={(e) => void onCreateMemory(e)}>
        <select
          value={memType}
          onChange={(e) => setMemType(e.target.value)}
        >
          {MEMORY_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>{" "}
        <input
          value={memContent}
          onChange={(e) => setMemContent(e.target.value)}
          placeholder="fact, event, joke…"
          style={{ width: "55%" }}
          required
        />{" "}
        <input
          type="number"
          min={0}
          max={1}
          step={0.1}
          value={memImportance}
          onChange={(e) => setMemImportance(e.target.value)}
          style={{ width: 64 }}
        />{" "}
        <button type="submit">store</button>
      </form>
      <p style={{ fontSize: 12, color: "#555" }}>
        Stored facts are injected into generation (most important first, up to 10)
        so the creator remembers its fictional history.
      </p>

      <h2>Visual identity (Sprint 5.2)</h2>
      {identity === null ? (
        <p>no identity yet (renders use plain cards)</p>
      ) : (
        <div>
          <p>
            <strong>{identity.display_name}</strong> · version {identity.version}
          </p>
          <p>
            accessories: {identity.accessories.join(", ") || "—"} · props:{" "}
            {identity.props.join(", ") || "—"}
          </p>
          <p style={{ fontSize: 12, color: "#555" }}>{identity.style}</p>
          <p>
            {Object.entries(identity.palette).map(([k, v]) => (
              <span key={k} style={{ marginRight: 12, fontSize: 12 }}>
                <span
                  style={{
                    display: "inline-block",
                    width: 12,
                    height: 12,
                    background: v,
                    border: "1px solid #999",
                    marginRight: 4,
                  }}
                />
                {k}
              </span>
            ))}
          </p>
          <img
            src={`${API_ROOT}/media/portraits/creator_${identity.creator_id}_${identity.version}/portrait.png`}
            alt={`${identity.display_name} portrait`}
            style={{ width: 135, height: 240, objectFit: "cover", background: "#000" }}
          />
          <p style={{ fontSize: 12, color: "#555" }}>
            (portrait renders on demand via the render flow)
          </p>
        </div>
      )}
    </main>
  );
}
