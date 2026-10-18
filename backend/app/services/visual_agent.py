"""Visual/social agent — perceive the emulator screen and act (roadmap 20.2).

The agent is shown a text rendering of the isolated emulator ("screen") and
returns one action per step via the provider abstraction. Every step's
observation, reasoning, and action is stored as an immutable trajectory so
agents can be evaluated separately from real-world platform policies. No action
touches a real platform.
"""
from sqlalchemy.orm import Session

from ..ai.prompts import render_agent_prompt
from ..ai.providers import (
    GenerateRequest,
    LLMProvider,
    ProviderError,
    get_provider,
)
from ..ai.structured_output import ParseError, parse_agent_action
from ..models.agent import AgentAction, AgentSession
from ..models.emulator import EmulatorAccount
from . import emulator_service as emu

AGENT_JSON_SCHEMA = (
    '{"action": "scroll|open|watch|read|comment|follow|profile|stop", '
    '"target_id": int|null, "handle": str|null, "body": str, '
    '"watch_seconds": number|null, "liked": bool|null, "reasoning": str}'
)
MAX_STEPS_LIMIT = 20
_FEED_PREVIEW = 8


def render_screen(
    db: Session,
    account: EmulatorAccount,
    open_post_id: int | None = None,
    profile_handle: str | None = None,
) -> str:
    """Render the current emulator state as a text 'screen' for the agent."""
    lines = [f"SCREEN — emulator feed viewed as @{account.handle}", ""]
    feed = emu.feed(db, account_handle=account.handle, limit=_FEED_PREVIEW)
    if not feed:
        lines.append("(feed is empty)")
    else:
        lines.append("Feed:")
        for post in feed:
            eng = post["engagement"]
            lines.append(
                f"[post #{post['id']}] @{post['author']} — {post['caption'] or '(no caption)'} "
                f"(views {eng['views']}, likes {eng['likes']}, comments {eng['comments']})"
            )

    if open_post_id is not None:
        try:
            detail = emu.post_detail(db, open_post_id)
        except ValueError:
            lines.append(f"\n(open post #{open_post_id} no longer exists)")
        else:
            lines.append("")
            lines.append(f"Open post #{detail['id']} by @{detail['author']}:")
            lines.append(f"  {detail['caption'] or '(no caption)'}")
            if detail["comments"]:
                lines.append("  Comments:")
                for c in detail["comments"]:
                    reply = " (reply)" if c["parent_id"] else ""
                    lines.append(f"    @{c['author']}{reply}: {c['body']}")
            else:
                lines.append("  (no comments yet)")

    if profile_handle:
        try:
            prof = emu.profile(db, profile_handle)
        except ValueError:
            lines.append(f"\n(profile @{profile_handle} not found)")
        else:
            lines.append("")
            lines.append(
                f"Profile @{prof['handle']} — {prof['followers']} followers, "
                f"{prof['following']} following, {prof['post_count']} posts"
            )
    return "\n".join(lines)


def _execute(
    db: Session,
    account: EmulatorAccount,
    action: str,
    target_id: int | None,
    handle: str | None,
    body: str,
    watch_seconds: float | None,
    liked: bool | None,
    state: dict,
) -> tuple[str, str]:
    """Apply one action; return (status, error)."""
    try:
        if action == "scroll":
            return "ok", ""
        if action == "stop":
            return "ok", ""
        if action in ("open", "read"):
            if target_id is None:
                return "error", "open/read requires a target_id"
            emu.post_detail(db, target_id)
            state["open_post_id"] = target_id
            return "ok", ""
        if action == "watch":
            if target_id is None:
                return "error", "watch requires a target_id"
            emu.record_view(
                db,
                target_id,
                account.handle,
                watch_seconds=watch_seconds if watch_seconds is not None else 0.0,
                liked=bool(liked),
            )
            state["open_post_id"] = target_id
            return "ok", ""
        if action == "comment":
            if target_id is None or not (body or "").strip():
                return "error", "comment requires a target_id and body"
            emu.add_comment(db, target_id, account.handle, body)
            return "ok", ""
        if action == "follow":
            if not handle:
                return "error", "follow requires a handle"
            emu.follow(db, account.handle, handle)
            return "ok", ""
        if action == "profile":
            if not handle:
                return "error", "profile requires a handle"
            emu.profile(db, handle)
            state["profile_handle"] = handle
            return "ok", ""
        return "error", f"unhandled action '{action}'"
    except ValueError as exc:
        return "error", str(exc)


def run_agent(
    db: Session,
    account_handle: str,
    goal: str = "",
    max_steps: int = 8,
    provider_name: str | None = None,
    prompt_version: str = "agent_action_v1",
    temperature: float = 0.4,
) -> AgentSession:
    """Run a step-by-step visual/social agent episode against the emulator."""
    account = emu.get_account(db, account_handle)
    if account is None:
        raise ValueError(f"account '{account_handle}' not found")
    max_steps = max(1, min(max_steps, MAX_STEPS_LIMIT))

    provider: LLMProvider = get_provider(provider_name)
    session = AgentSession(
        account_handle=account.handle,
        goal=goal,
        environment="emulator",
        provider=provider.name,
        model="",
        prompt_version=prompt_version,
        max_steps=max_steps,
    )
    db.add(session)
    db.flush()

    state: dict = {"open_post_id": None, "profile_handle": None}
    stopped_reason = "max_steps"
    model_name = ""

    for step in range(max_steps):
        screen = render_screen(db, account, state["open_post_id"], state["profile_handle"])
        system_prompt = render_agent_prompt(
            handle=account.handle,
            goal=goal,
            screen=screen,
            json_schema=AGENT_JSON_SCHEMA,
            step=step,
            max_steps=max_steps,
            version=prompt_version,
        )
        try:
            response = provider.generate(
                GenerateRequest(
                    system_prompt=system_prompt,
                    user_message=screen,
                    response_format="agent_action",
                    variant=step,
                    temperature=temperature,
                    max_tokens=200,
                )
            )
        except ProviderError as exc:
            _record(db, session, step, "stop", None, None, "", None, None, "", screen, "error", str(exc))
            stopped_reason = "provider_error"
            break
        model_name = response.model

        try:
            draft = parse_agent_action(response.text)
        except ParseError as exc:
            _record(db, session, step, "stop", None, None, "", None, None, "", screen, "error", str(exc))
            stopped_reason = "parse_error"
            break

        status, error = _execute(
            db, account, draft.action, draft.target_id, draft.handle,
            draft.body, draft.watch_seconds, draft.liked, state,
        )
        _record(
            db, session, step, draft.action, draft.target_id, draft.handle,
            draft.body, draft.watch_seconds, draft.liked, draft.reasoning,
            screen, status, error,
        )
        session.step_count = step + 1
        if draft.action == "stop":
            stopped_reason = "stopped"
            break

    session.stopped_reason = stopped_reason
    session.model = model_name
    db.commit()
    db.refresh(session)
    return session


def _record(
    db: Session,
    session: AgentSession,
    step: int,
    action: str,
    target_id: int | None,
    handle: str | None,
    body: str,
    watch_seconds: float | None,
    liked: bool | None,
    reasoning: str,
    observation: str,
    status: str,
    error: str,
) -> None:
    db.add(
        AgentAction(
            session_id=session.id,
            step_index=step,
            action=action,
            target_id=target_id,
            handle=handle,
            body=body,
            watch_seconds=watch_seconds,
            liked=liked,
            reasoning=reasoning,
            observation=observation,
            status=status,
            error=error,
        )
    )


def session_detail(db: Session, session_id: int) -> dict:
    session = db.get(AgentSession, session_id)
    if session is None:
        raise ValueError("agent session not found")
    actions = (
        db.query(AgentAction)
        .filter(AgentAction.session_id == session_id)
        .order_by(AgentAction.step_index)
        .all()
    )
    return {
        "id": session.id,
        "account_handle": session.account_handle,
        "goal": session.goal,
        "environment": session.environment,
        "provider": session.provider,
        "model": session.model,
        "prompt_version": session.prompt_version,
        "max_steps": session.max_steps,
        "step_count": session.step_count,
        "stopped_reason": session.stopped_reason,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "actions": [
            {
                "step_index": a.step_index,
                "action": a.action,
                "target_id": a.target_id,
                "handle": a.handle,
                "body": a.body,
                "watch_seconds": a.watch_seconds,
                "liked": a.liked,
                "reasoning": a.reasoning,
                "observation": a.observation,
                "status": a.status,
                "error": a.error,
            }
            for a in actions
        ],
    }


def list_sessions(db: Session) -> list[AgentSession]:
    return db.query(AgentSession).order_by(AgentSession.id.desc()).all()
