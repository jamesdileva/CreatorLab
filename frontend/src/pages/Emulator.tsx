import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  addComment,
  createAccount,
  createPost,
  follow,
  getFeed,
  getPost,
  getProfile,
  listAccounts,
  recordView,
  runAgent,
  syncCreatorAccounts,
} from "../services/emulator";
import type {
  EmulatorAccount,
  EmulatorPost,
  EmulatorPostDetail,
  EmulatorProfile,
  AgentSession,
} from "../services/emulator";

export default function Emulator() {
  const [accounts, setAccounts] = useState<EmulatorAccount[]>([]);
  const [active, setActive] = useState("");
  const [feed, setFeed] = useState<EmulatorPost[]>([]);
  const [selected, setSelected] = useState<EmulatorPostDetail | null>(null);
  const [profile, setProfile] = useState<EmulatorProfile | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const [newHandle, setNewHandle] = useState("");
  const [newKind, setNewKind] = useState("viewer");
  const [caption, setCaption] = useState("");
  const [commentBody, setCommentBody] = useState("");
  const [followTarget, setFollowTarget] = useState("");
  const [agentGoal, setAgentGoal] = useState("Explore the feed and engage naturally.");
  const [agentRun, setAgentRun] = useState<AgentSession | null>(null);

  const loadAccounts = () =>
    listAccounts()
      .then((rows) => {
        setAccounts(rows);
        if (!active && rows.length) setActive(rows[0].handle);
      })
      .catch(() => setAccounts([]));

  const loadFeed = (handle?: string) =>
    getFeed(handle || active || undefined)
      .then(setFeed)
      .catch(() => setFeed([]));

  useEffect(() => {
    void loadAccounts();
    void loadFeed();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "action failed");
    } finally {
      setBusy(false);
    }
  };

  const onSync = () =>
    run(async () => {
      setAccounts(await syncCreatorAccounts());
      await loadFeed();
    });

  const onCreateAccount = (e: React.FormEvent) => {
    e.preventDefault();
    void run(async () => {
      await createAccount({ handle: newHandle, kind: newKind });
      setNewHandle("");
      await loadAccounts();
    });
  };

  const onPublish = (e: React.FormEvent) => {
    e.preventDefault();
    if (!active) return;
    void run(async () => {
      const post = await createPost({ author: active, caption });
      setCaption("");
      setSelected(post);
      await loadFeed();
    });
  };

  const openPost = (id: number) =>
    run(async () => {
      setSelected(await getPost(id));
    });

  const onComment = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selected || !active) return;
    void run(async () => {
      const post = await addComment(selected.id, { author: active, body: commentBody });
      setCommentBody("");
      setSelected(post);
      await loadFeed();
    });
  };

  const onLike = () => {
    if (!selected || !active) return;
    void run(async () => {
      setSelected(await recordView(selected.id, { account: active, watch_seconds: 9, liked: true }));
      await loadFeed();
    });
  };

  const onFollow = (e: React.FormEvent) => {
    e.preventDefault();
    if (!active || !followTarget) return;
    void run(async () => {
      await follow(active, followTarget);
      setFollowTarget("");
      await loadFeed(active);
    });
  };

  const openProfile = (handle: string) =>
    run(async () => {
      setProfile(await getProfile(handle));
    });

  const onRunAgent = (e: React.FormEvent) => {
    e.preventDefault();
    if (!active) return;
    void run(async () => {
      const session = await runAgent(active, agentGoal);
      setAgentRun(session);
      await loadFeed(active);
    });
  };

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 900 }}>
      <p>
        <Link to="/dashboard">← Dashboard</Link>
      </p>
      <h1>Emulator laboratory (Sprint 20.1)</h1>
      <p style={{ fontSize: 12, color: "#555" }}>
        A controlled fake social app — feed, video, comment, profile, follow —
        that never touches a real platform. A safe sandbox for agent interaction
        experiments.
      </p>
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      <section style={{ border: "1px solid #ccc", borderRadius: 8, padding: 12 }}>
        <h2>Accounts</h2>
        <p>
          acting as{" "}
          <select value={active} onChange={(e) => setActive(e.target.value)}>
            {accounts.length === 0 && <option value="">(none)</option>}
            {accounts.map((a) => (
              <option key={a.id} value={a.handle}>
                @{a.handle} ({a.kind})
              </option>
            ))}
          </select>{" "}
          <button disabled={busy} onClick={() => void onSync()}>
            sync creator accounts
          </button>{" "}
          <button disabled={busy} onClick={() => void loadFeed(active)}>
            refresh feed
          </button>
        </p>
        <form onSubmit={onCreateAccount}>
          <input
            placeholder="handle"
            value={newHandle}
            onChange={(e) => setNewHandle(e.target.value)}
          />
          <select value={newKind} onChange={(e) => setNewKind(e.target.value)}>
            <option value="viewer">viewer</option>
            <option value="creator">creator</option>
            <option value="agent">agent</option>
          </select>
          <button disabled={busy || !newHandle} type="submit">
            create account
          </button>
        </form>
        <form onSubmit={onFollow} style={{ marginTop: 8 }}>
          <input
            placeholder="follow @handle"
            value={followTarget}
            onChange={(e) => setFollowTarget(e.target.value)}
          />
          <button disabled={busy || !followTarget || !active} type="submit">
            follow
          </button>
        </form>
      </section>

      <section style={{ border: "1px solid #ccc", borderRadius: 8, padding: 12, marginTop: 12 }}>
        <h2>Compose</h2>
        <form onSubmit={onPublish}>
          <input
            style={{ width: "70%" }}
            placeholder={`new video caption as @${active || "?"}`}
            value={caption}
            onChange={(e) => setCaption(e.target.value)}
          />
          <button disabled={busy || !active || !caption} type="submit">
            post
          </button>
        </form>
      </section>

      <section style={{ border: "1px solid #ccc", borderRadius: 8, padding: 12, marginTop: 12 }}>
        <h2>Feed</h2>
        {feed.length === 0 ? (
          <p>empty feed — post something or follow an account</p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0 }}>
            {feed.map((p) => (
              <li key={p.id} style={{ borderBottom: "1px solid #eee", padding: "6px 0" }}>
                <button onClick={() => void openPost(p.id)} style={{ all: "unset", cursor: "pointer" }}>
                  <strong>@{p.author}</strong> — {p.caption || "(no caption)"}
                </button>
                <span style={{ fontSize: 12, color: "#555", marginLeft: 8 }}>
                  ▶ {p.engagement.views} · ♥ {p.engagement.likes} · 💬 {p.engagement.comments}
                </span>{" "}
                <button onClick={() => void openProfile(p.author)}>profile</button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {selected && (
        <section style={{ border: "1px solid #333", borderRadius: 8, padding: 12, marginTop: 12 }}>
          <h2>
            Post #{selected.id} by @{selected.author}
          </h2>
          <p>{selected.caption || "(no caption)"}</p>
          <p style={{ fontSize: 12, color: "#555" }}>
            ▶ {selected.engagement.views} · ♥ {selected.engagement.likes} · 💬{" "}
            {selected.engagement.comments}
          </p>
          <button disabled={busy || !active} onClick={() => void onLike()}>
            watch + like as @{active}
          </button>
          <h3>Comments</h3>
          {selected.comments.length === 0 ? (
            <p>no comments</p>
          ) : (
            <ul>
              {selected.comments.map((c) => (
                <li key={c.id}>
                  <strong>@{c.author}</strong>: {c.body}
                  {c.parent_id ? " (reply)" : ""}
                </li>
              ))}
            </ul>
          )}
          <form onSubmit={onComment}>
            <input
              style={{ width: "70%" }}
              placeholder={`comment as @${active || "?"}`}
              value={commentBody}
              onChange={(e) => setCommentBody(e.target.value)}
            />
            <button disabled={busy || !active || !commentBody} type="submit">
              comment
            </button>
          </form>
        </section>
      )}

      {profile && (
        <section style={{ border: "1px solid #333", borderRadius: 8, padding: 12, marginTop: 12 }}>
          <h2>
            @{profile.handle} ({profile.kind})
          </h2>
          <p>
            {profile.followers} followers · {profile.following} following ·{" "}
            {profile.post_count} posts
          </p>
          <ul>
            {profile.posts.map((p) => (
              <li key={p.id}>{p.caption || "(no caption)"}</li>
            ))}
          </ul>
          <button onClick={() => setProfile(null)}>close profile</button>
        </section>
      )}

      <section style={{ border: "1px solid #333", borderRadius: 8, padding: 12, marginTop: 12 }}>
        <h2>Visual/social agent (Sprint 20.2)</h2>
        <p style={{ fontSize: 12, color: "#555" }}>
          An agent perceives the emulator as a rendered screen and acts one step
          at a time (open → watch → read → comment → navigate). Runs on the
          configured provider (stub or a local Ollama model) — separate from any
          real platform.
        </p>
        <form onSubmit={onRunAgent}>
          <input
            style={{ width: "60%" }}
            placeholder="agent goal"
            value={agentGoal}
            onChange={(e) => setAgentGoal(e.target.value)}
          />
          <button disabled={busy || !active} type="submit">
            run agent as @{active}
          </button>
        </form>

        {agentRun && (
          <div style={{ marginTop: 8 }}>
            <p style={{ fontSize: 12, color: "#555" }}>
              session #{agentRun.id} · {agentRun.provider}/{agentRun.model || "?"} ·{" "}
              {agentRun.step_count} steps · {agentRun.stopped_reason}
            </p>
            <ol>
              {agentRun.actions.map((a) => (
                <li key={a.step_index}>
                  <strong>{a.action}</strong>
                  {a.target_id != null ? ` #${a.target_id}` : ""}
                  {a.handle ? ` @${a.handle}` : ""}
                  {a.body ? `: “${a.body}”` : ""}
                  {a.status !== "ok" ? ` — error: ${a.error}` : ""}
                  {a.reasoning ? ` (${a.reasoning})` : ""}
                </li>
              ))}
            </ol>
          </div>
        )}
      </section>
    </main>
  );
}
