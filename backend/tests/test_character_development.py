"""Sprint 22.2 — character development (evolving traits + arc)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.providers import GenerateResponse
from app.core.database import Base, get_db
from app.main import app
from app.models.creator import Creator
from app.models.episode import Episode, EpisodeStatus
from app.models.series import Series
from app.services import character_development as svc
from app.services import creator_service

test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


def _override_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = _override_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def _db():
    return TestingSession()


def _seed(name="Hank", slug="hank"):
    db = _db()
    creator = Creator(name=name, slug=slug)
    db.add(creator)
    db.flush()
    series = Series(creator_id=creator.id, name=f"{name}'s World")
    db.add(series)
    db.commit()
    out = (creator.id, series.id)
    db.close()
    return out


def _episode(creator_id, series_id, number=1):
    db = _db()
    ep = Episode(
        creator_id=creator_id, series_id=series_id, episode_number=number,
        title=f"Ep {number}", status=EpisodeStatus.IDEA,
    )
    db.add(ep)
    db.commit()
    out = ep.id
    db.close()
    return out


# ---------- arc ----------


def test_character_arc(client):
    cid, _ = _seed()
    db = _db()
    svc.define_trait(db, cid, "ai_stance", "anti_ai")
    svc.record_development(
        db, cid, "ai_stance", "cautiously_accepts", "episode 3 forced him to rely on AI"
    )
    svc.record_development(
        db, cid, "ai_stance", "automation_interested", "the AI saved the harvest"
    )
    arc = svc.character_arc(db, cid)
    db.close()

    assert len(arc["traits"]) == 1
    assert arc["traits"][0]["value"] == "automation_interested"
    assert arc["traits"][0]["stage"] == 2
    assert arc["arcs"][0]["path"] == [
        "anti_ai", "cautiously_accepts", "automation_interested",
    ]
    assert arc["arcs"][0]["text"].startswith("ai_stance: anti_ai ->")
    assert len(arc["history"]) == 3  # initial + 2 developments


def test_development_requires_reason(client):
    cid, _ = _seed()
    db = _db()
    svc.define_trait(db, cid, "ai_stance", "anti_ai")
    with pytest.raises(ValueError):
        svc.record_development(db, cid, "ai_stance", "cautiously_accepts", "   ")
    db.close()


def test_development_rejects_unchanged_value(client):
    cid, _ = _seed()
    db = _db()
    svc.define_trait(db, cid, "ai_stance", "anti_ai")
    with pytest.raises(ValueError):
        svc.record_development(db, cid, "ai_stance", "anti_ai", "no change")
    db.close()


def test_development_requires_defined_trait(client):
    cid, _ = _seed()
    db = _db()
    with pytest.raises(ValueError):
        svc.record_development(db, cid, "missing", "x", "because")
    db.close()


def test_duplicate_define_rejected(client):
    cid, _ = _seed()
    db = _db()
    svc.define_trait(db, cid, "ai_stance", "anti_ai")
    with pytest.raises(ValueError):
        svc.define_trait(db, cid, "ai_stance", "pro_ai")
    db.close()


# ---------- evidence + prompt injection ----------


def test_episode_evidence_links_and_validates(client):
    cid, sid = _seed()
    ep_id = _episode(cid, sid, 1)
    other_cid, other_sid = _seed("Alex", "alex-exe")
    foreign_ep = _episode(other_cid, other_sid, 1)

    db = _db()
    svc.define_trait(db, cid, "ai_stance", "anti_ai")
    row = svc.record_development(
        db, cid, "ai_stance", "cautiously_accepts", "the tractor incident",
        episode_id=ep_id,
    )
    assert row.episode_id == ep_id
    with pytest.raises(ValueError):
        svc.record_development(
            db, cid, "ai_stance", "automation_interested", "borrowed episode",
            episode_id=foreign_ep,
        )
    db.close()


def test_character_context_and_voice_prompt(client):
    cid, _ = _seed()
    db = _db()
    svc.define_trait(db, cid, "ai_stance", "anti_ai")
    svc.record_development(db, cid, "ai_stance", "cautiously_accepts", "the incident")
    block = svc.character_context(db, cid)
    assert "Character development" in block
    assert "ai_stance: cautiously_accepts (changed 1x)" in block
    db.close()

    captured: dict = {}

    class Capture:
        name = "capture"

        def generate(self, request):
            captured["system_prompt"] = request.system_prompt
            return GenerateResponse(text="ok", model="capture")

    original = creator_service.get_provider
    creator_service.get_provider = lambda name=None: Capture()
    try:
        db = _db()
        creator = db.get(Creator, cid)
        creator_service.generate_creator_response(db, creator, "how do you feel about AI?")
        db.close()
    finally:
        creator_service.get_provider = original

    assert "Character development" in captured["system_prompt"]
    assert "cautiously_accepts" in captured["system_prompt"]


# ---------- endpoints ----------


def test_endpoints(client):
    cid, _ = _seed()
    defined = client.post(
        f"/api/character-development/creators/{cid}/traits",
        json={"trait": "ai_stance", "value": "anti_ai"},
    )
    assert defined.status_code == 201, defined.text

    made = client.post(
        f"/api/character-development/creators/{cid}/developments",
        json={
            "trait": "ai_stance",
            "to_value": "cautiously_accepts",
            "reason": "episode 2",
        },
    )
    assert made.status_code == 201, made.text
    assert made.json()["from_value"] == "anti_ai"

    arc = client.get(f"/api/character-development/creators/{cid}").json()
    assert arc["traits"][0]["value"] == "cautiously_accepts"

    hist = client.get(
        f"/api/character-development/creators/{cid}/traits/ai_stance"
    ).json()
    assert len(hist["history"]) == 2

    bad = client.post(
        f"/api/character-development/creators/{cid}/developments",
        json={"trait": "ai_stance", "to_value": "x", "reason": ""},
    )
    assert bad.status_code == 400
    assert client.get("/api/character-development/creators/999").status_code == 404
    assert (
        client.get(
            f"/api/character-development/creators/{cid}/traits/nope"
        ).status_code
        == 404
    )
