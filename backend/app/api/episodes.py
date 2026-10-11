"""Story-universe API — Series/Episode/Scene/StoryThread/Canon (Sprint 2.1).

Delete semantics follow the experiment-first design: deleting a series marks it
ENDED and deleting an episode ARCHIVES it, so history stays viewable.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..ai.structured_output import ParseError
from ..core.database import get_db
from ..models.canon import Canon, CanonCategory
from ..models.concept import Concept, ConceptSet
from ..models.concept_score import ConceptScore, HumanRanking
from ..models.creator import Creator
from ..models.episode import Episode, EpisodeStatus
from ..models.scene import Scene
from ..models.series import Series, SeriesStatus
from ..models.story_thread import StoryThread, ThreadStatus
from ..services.concept_service import ConceptsBlockedError, generate_concepts
from ..services.episode_service import (
    EpisodeBlockedError,
    GenerationResult,
    generate_episode,
)
from ..services.scoring_service import (
    SCORER_VERSION,
    compare_with_human,
    record_human_ranking,
    score_concept_set,
)

router = APIRouter(tags=["story-universe"])


# ---------- shared helpers ----------


def _parse_enum(enum_cls, value: str, field: str):
    try:
        return enum_cls(value.strip().upper())
    except ValueError:
        valid = sorted(t.value for t in enum_cls)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field} must be one of {valid}",
        )


def _series_or_404(db: Session, series_id: int) -> Series:
    series = db.get(Series, series_id)
    if series is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="series not found")
    return series


def _episode_or_404(db: Session, episode_id: int) -> Episode:
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="episode not found")
    return episode


# ---------- Series ----------


class SeriesCreate(BaseModel):
    creator_id: int
    name: str
    description: str = ""


class SeriesUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None


class SeriesRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creator_id: int
    name: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime


@router.post("/api/series", status_code=status.HTTP_201_CREATED, response_model=SeriesRead)
def create_series(payload: SeriesCreate, db: Session = Depends(get_db)) -> Series:
    if db.get(Creator, payload.creator_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="creator not found")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")
    series = Series(creator_id=payload.creator_id, name=name, description=payload.description)
    db.add(series)
    db.commit()
    db.refresh(series)
    return series


@router.get("/api/series", response_model=list[SeriesRead])
def list_series(creator_id: int | None = None, db: Session = Depends(get_db)) -> list[Series]:
    q = db.query(Series)
    if creator_id is not None:
        q = q.filter(Series.creator_id == creator_id)
    return q.order_by(Series.id).all()


@router.get("/api/series/{series_id}", response_model=SeriesRead)
def get_series(series_id: int, db: Session = Depends(get_db)) -> Series:
    return _series_or_404(db, series_id)


@router.patch("/api/series/{series_id}", response_model=SeriesRead)
def update_series(series_id: int, payload: SeriesUpdate, db: Session = Depends(get_db)) -> Series:
    series = _series_or_404(db, series_id)
    patch = payload.model_dump(exclude_unset=True)
    if patch.get("name") is not None:
        patch["name"] = patch["name"].strip()
        if not patch["name"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")
    if patch.get("status") is not None:
        patch["status"] = _parse_enum(SeriesStatus, patch["status"], "status")
    for key, value in patch.items():
        if value is not None:
            setattr(series, key, value)
    db.commit()
    db.refresh(series)
    return series


@router.delete("/api/series/{series_id}", response_model=SeriesRead)
def end_series(series_id: int, db: Session = Depends(get_db)) -> Series:
    series = _series_or_404(db, series_id)
    series.status = SeriesStatus.ENDED
    db.commit()
    db.refresh(series)
    return series


# ---------- Episodes ----------


class EpisodeCreate(BaseModel):
    title: str
    episode_number: int | None = None
    premise: str = ""
    synopsis: str = ""


class EpisodeUpdate(BaseModel):
    title: str | None = None
    premise: str | None = None
    synopsis: str | None = None
    script: str | None = None
    status: str | None = None


class EpisodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creator_id: int
    series_id: int
    episode_number: int
    title: str
    premise: str
    synopsis: str
    script: str
    status: str
    created_at: datetime
    updated_at: datetime


@router.post(
    "/api/series/{series_id}/episodes",
    status_code=status.HTTP_201_CREATED,
    response_model=EpisodeRead,
)
def create_episode(
    series_id: int, payload: EpisodeCreate, db: Session = Depends(get_db)
) -> Episode:
    series = _series_or_404(db, series_id)
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="title is required")
    if payload.episode_number is None:
        number = (
            db.query(func.max(Episode.episode_number))
            .filter(Episode.series_id == series_id)
            .scalar()
            or 0
        ) + 1
    else:
        if payload.episode_number < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="episode_number must be >= 1"
            )
        clash = (
            db.query(Episode)
            .filter(
                Episode.series_id == series_id,
                Episode.episode_number == payload.episode_number,
            )
            .first()
        )
        if clash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="episode_number already used in this series",
            )
        number = payload.episode_number
    episode = Episode(
        creator_id=series.creator_id,
        series_id=series_id,
        episode_number=number,
        title=title,
        premise=payload.premise,
        synopsis=payload.synopsis,
        status=EpisodeStatus.IDEA,
    )
    db.add(episode)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="episode_number already used in this series",
        )
    db.refresh(episode)
    return episode


@router.get("/api/series/{series_id}/episodes", response_model=list[EpisodeRead])
def list_episode_history(series_id: int, db: Session = Depends(get_db)) -> list[Episode]:
    _series_or_404(db, series_id)
    return (
        db.query(Episode)
        .filter(Episode.series_id == series_id)
        .order_by(Episode.episode_number)
        .all()
    )


@router.get("/api/episodes", response_model=list[EpisodeRead])
def list_episodes(series_id: int | None = None, db: Session = Depends(get_db)) -> list[Episode]:
    q = db.query(Episode)
    if series_id is not None:
        q = q.filter(Episode.series_id == series_id)
    return q.order_by(Episode.series_id, Episode.episode_number).all()


@router.get("/api/episodes/{episode_id}", response_model=EpisodeRead)
def get_episode(episode_id: int, db: Session = Depends(get_db)) -> Episode:
    return _episode_or_404(db, episode_id)


@router.patch("/api/episodes/{episode_id}", response_model=EpisodeRead)
def update_episode(
    episode_id: int, payload: EpisodeUpdate, db: Session = Depends(get_db)
) -> Episode:
    episode = _episode_or_404(db, episode_id)
    patch = payload.model_dump(exclude_unset=True)
    if patch.get("title") is not None:
        patch["title"] = patch["title"].strip()
        if not patch["title"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="title is required")
    if patch.get("status") is not None:
        patch["status"] = _parse_enum(EpisodeStatus, patch["status"], "status")
    for key, value in patch.items():
        if value is not None:
            setattr(episode, key, value)
    db.commit()
    db.refresh(episode)
    return episode


@router.delete("/api/episodes/{episode_id}", response_model=EpisodeRead)
def archive_episode(episode_id: int, db: Session = Depends(get_db)) -> Episode:
    episode = _episode_or_404(db, episode_id)
    episode.status = EpisodeStatus.ARCHIVED
    db.commit()
    db.refresh(episode)
    return episode


# ---------- Scenes ----------


class SceneCreate(BaseModel):
    title: str = ""
    direction: str = ""
    scene_number: int | None = None


class SceneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    episode_id: int
    scene_number: int
    title: str
    direction: str
    created_at: datetime


@router.post(
    "/api/episodes/{episode_id}/scenes",
    status_code=status.HTTP_201_CREATED,
    response_model=SceneRead,
)
def create_scene(
    episode_id: int, payload: SceneCreate, db: Session = Depends(get_db)
) -> Scene:
    _episode_or_404(db, episode_id)
    if payload.scene_number is None:
        number = (
            db.query(func.max(Scene.scene_number))
            .filter(Scene.episode_id == episode_id)
            .scalar()
            or 0
        ) + 1
    else:
        number = payload.scene_number
        if number < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="scene_number must be >= 1"
            )
    scene = Scene(
        episode_id=episode_id,
        scene_number=number,
        title=payload.title.strip(),
        direction=payload.direction,
    )
    db.add(scene)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="scene_number already used in this episode",
        )
    db.refresh(scene)
    return scene


@router.get("/api/episodes/{episode_id}/scenes", response_model=list[SceneRead])
def list_scenes(episode_id: int, db: Session = Depends(get_db)) -> list[Scene]:
    _episode_or_404(db, episode_id)
    return (
        db.query(Scene)
        .filter(Scene.episode_id == episode_id)
        .order_by(Scene.scene_number)
        .all()
    )


@router.delete("/api/scenes/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scene(scene_id: int, db: Session = Depends(get_db)) -> None:
    scene = db.get(Scene, scene_id)
    if scene is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scene not found")
    db.delete(scene)
    db.commit()


# ---------- Story threads ----------


class ThreadCreate(BaseModel):
    title: str
    description: str = ""
    introduced_episode_id: int | None = None


class ThreadUpdate(BaseModel):
    status: str | None = None
    resolved_episode_id: int | None = None
    title: str | None = None


class ThreadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    series_id: int
    title: str
    description: str
    status: str
    introduced_episode_id: int | None
    resolved_episode_id: int | None
    created_at: datetime


@router.post(
    "/api/series/{series_id}/threads",
    status_code=status.HTTP_201_CREATED,
    response_model=ThreadRead,
)
def create_thread(
    series_id: int, payload: ThreadCreate, db: Session = Depends(get_db)
) -> StoryThread:
    _series_or_404(db, series_id)
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="title is required")
    if payload.introduced_episode_id is not None:
        ep = _episode_or_404(db, payload.introduced_episode_id)
        if ep.series_id != series_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="introduced_episode_id belongs to another series",
            )
    thread = StoryThread(
        series_id=series_id,
        title=title,
        description=payload.description,
        status=ThreadStatus.OPEN,
        introduced_episode_id=payload.introduced_episode_id,
    )
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return thread


@router.get("/api/series/{series_id}/threads", response_model=list[ThreadRead])
def list_threads(
    series_id: int, status: str | None = None, db: Session = Depends(get_db)
) -> list[StoryThread]:
    _series_or_404(db, series_id)
    q = db.query(StoryThread).filter(StoryThread.series_id == series_id)
    if status is not None:
        q = q.filter(StoryThread.status == _parse_enum(ThreadStatus, status, "status"))
    return q.order_by(StoryThread.id).all()


@router.patch("/api/threads/{thread_id}", response_model=ThreadRead)
def update_thread(
    thread_id: int, payload: ThreadUpdate, db: Session = Depends(get_db)
) -> StoryThread:
    thread = db.get(StoryThread, thread_id)
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="thread not found")
    patch = payload.model_dump(exclude_unset=True)
    if patch.get("status") is not None:
        patch["status"] = _parse_enum(ThreadStatus, patch["status"], "status")
        if patch["status"] == ThreadStatus.RESOLVED and patch.get("resolved_episode_id") is None:
            if thread.resolved_episode_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="resolving a thread requires resolved_episode_id",
                )
    if patch.get("resolved_episode_id") is not None:
        ep = _episode_or_404(db, patch["resolved_episode_id"])
        if ep.series_id != thread.series_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="resolved_episode_id belongs to another series",
            )
    for key, value in patch.items():
        if value is not None:
            setattr(thread, key, value)
    db.commit()
    db.refresh(thread)
    return thread


@router.delete("/api/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_thread(thread_id: int, db: Session = Depends(get_db)) -> None:
    thread = db.get(StoryThread, thread_id)
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="thread not found")
    db.delete(thread)
    db.commit()


# ---------- Canon ----------


class CanonCreate(BaseModel):
    category: str
    statement: str


class CanonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    series_id: int
    category: str
    statement: str
    created_at: datetime


@router.post(
    "/api/series/{series_id}/canon",
    status_code=status.HTTP_201_CREATED,
    response_model=CanonRead,
)
def create_canon(series_id: int, payload: CanonCreate, db: Session = Depends(get_db)) -> Canon:
    _series_or_404(db, series_id)
    category = _parse_enum(CanonCategory, payload.category, "category")
    statement = payload.statement.strip()
    if not statement:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="statement is required"
        )
    canon = Canon(series_id=series_id, category=category, statement=statement)
    db.add(canon)
    db.commit()
    db.refresh(canon)
    return canon


@router.get("/api/series/{series_id}/canon", response_model=list[CanonRead])
def list_canon(series_id: int, db: Session = Depends(get_db)) -> list[Canon]:
    _series_or_404(db, series_id)
    return db.query(Canon).filter(Canon.series_id == series_id).order_by(Canon.id).all()


@router.delete("/api/canon/{canon_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_canon(canon_id: int, db: Session = Depends(get_db)) -> None:
    canon = db.get(Canon, canon_id)
    if canon is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="canon not found")
    db.delete(canon)
    db.commit()


# ---------- Concept generation (Sprint 3.1) ----------


class GenerateConceptsIn(BaseModel):
    topic: str
    count: int = 5
    prompt_version: str | None = None
    provider: str | None = None


class ConceptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    set_id: int
    index: int
    title: str
    premise: str
    hook: str
    angle: str
    tags: str
    created_at: datetime


class ConceptSetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creator_id: int
    series_id: int | None
    topic: str
    prompt_version: str
    provider: str
    model: str
    created_at: datetime


class GenerateConceptsOut(BaseModel):
    set: ConceptSetRead
    concepts: list[ConceptRead]
    evaluation_status: str
    issues: list[IssueRead]
    prompt_version: str
    provider: str
    model: str


@router.post("/api/series/{series_id}/generate-concepts", response_model=GenerateConceptsOut)
def generate_concepts_endpoint(
    series_id: int, payload: GenerateConceptsIn, db: Session = Depends(get_db)
) -> GenerateConceptsOut:
    series = _series_or_404(db, series_id)
    creator = db.get(Creator, series.creator_id)
    if creator is None or not creator.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="creator is missing or inactive",
        )
    topic = payload.topic.strip()
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="topic is required"
        )
    try:
        result = generate_concepts(
            db,
            series,
            creator,
            topic,
            count=payload.count,
            prompt_version=payload.prompt_version,
            provider_name=payload.provider,
        )
    except ConceptsBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "concept set blocked by evaluation; not persisted",
                "issues": [
                    {"code": i.code, "severity": i.severity.value, "detail": i.detail}
                    for i in exc.evaluation.issues
                ],
            },
        )
    except ParseError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown prompt version: {exc}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return GenerateConceptsOut(
        set=ConceptSetRead.model_validate(result.set),
        concepts=[ConceptRead.model_validate(c) for c in result.concepts],
        evaluation_status=result.evaluation.status,
        issues=[
            IssueRead(code=i.code, severity=i.severity.value, detail=i.detail)
            for i in result.evaluation.issues
        ],
        prompt_version=result.prompt_version,
        provider=result.provider,
        model=result.model,
    )


@router.get("/api/series/{series_id}/concept-sets", response_model=list[ConceptSetRead])
def list_concept_sets(series_id: int, db: Session = Depends(get_db)) -> list[ConceptSet]:
    _series_or_404(db, series_id)
    return (
        db.query(ConceptSet)
        .filter(ConceptSet.series_id == series_id)
        .order_by(ConceptSet.id.desc())
        .all()
    )


@router.get("/api/concept-sets/{set_id}/concepts", response_model=list[ConceptRead])
def list_concepts(set_id: int, db: Session = Depends(get_db)) -> list[Concept]:
    concept_set = db.get(ConceptSet, set_id)
    if concept_set is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="concept set not found")
    return (
        db.query(Concept)
        .filter(Concept.set_id == set_id)
        .order_by(Concept.index)
        .all()
    )


# ---------- Concept scoring + human comparison (Sprint 3.2) ----------


class ConceptScoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    concept_id: int
    set_id: int
    rank: int
    hook_score: float
    character_fit_score: float
    novelty_score: float
    story_potential_score: float
    audience_relevance_score: float
    episode_continuity_score: float
    composite: float
    scorer_version: str
    created_at: datetime


class ScoredConceptRead(BaseModel):
    concept: ConceptRead
    rank: int
    scores: dict[str, float]
    composite: float


class ScoreSetOut(BaseModel):
    set: ConceptSetRead
    scorer_version: str
    ranked: list[ScoredConceptRead]


class HumanRankingIn(BaseModel):
    order: list[int]
    note: str = ""


class HumanRankingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    set_id: int
    order: str
    note: str
    created_at: datetime


class ComparisonOut(BaseModel):
    system_order: list[int]
    human_order: list[int]
    agreement: dict
    correlation: dict
    system_top: int
    human_top: int
    sample_size: int


def _set_or_404(db: Session, set_id: int) -> ConceptSet:
    concept_set = db.get(ConceptSet, set_id)
    if concept_set is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="concept set not found"
        )
    return concept_set


@router.post("/api/concept-sets/{set_id}/score", response_model=ScoreSetOut)
def score_set(set_id: int, db: Session = Depends(get_db)) -> ScoreSetOut:
    concept_set = _set_or_404(db, set_id)
    creator = db.get(Creator, concept_set.creator_id)
    if creator is None or not creator.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="creator is missing or inactive",
        )
    try:
        results = score_concept_set(db, concept_set, creator)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return ScoreSetOut(
        set=ConceptSetRead.model_validate(concept_set),
        scorer_version=SCORER_VERSION,
        ranked=[
            ScoredConceptRead(
                concept=ConceptRead.model_validate(r.concept),
                rank=r.rank,
                scores=r.scores,
                composite=r.composite,
            )
            for r in results
        ],
    )


@router.get("/api/concept-sets/{set_id}/scores", response_model=list[ConceptScoreRead])
def list_scores(set_id: int, db: Session = Depends(get_db)) -> list[ConceptScore]:
    _set_or_404(db, set_id)
    return (
        db.query(ConceptScore)
        .filter(ConceptScore.set_id == set_id)
        .order_by(ConceptScore.rank)
        .all()
    )


@router.post(
    "/api/concept-sets/{set_id}/human-ranking",
    status_code=status.HTTP_201_CREATED,
    response_model=HumanRankingRead,
)
def record_human_ranking_endpoint(
    set_id: int, payload: HumanRankingIn, db: Session = Depends(get_db)
) -> HumanRanking:
    concept_set = _set_or_404(db, set_id)
    try:
        return record_human_ranking(db, concept_set, payload.order, payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/api/concept-sets/{set_id}/comparison", response_model=ComparisonOut | None)
def get_comparison(set_id: int, db: Session = Depends(get_db)) -> ComparisonOut | None:
    concept_set = _set_or_404(db, set_id)
    result = compare_with_human(db, concept_set)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="score the set and record a human ranking first",
        )
    return ComparisonOut(**result)


# ---------- Episode generation (Sprint 2.2) ----------


class GenerateEpisodeIn(BaseModel):
    variant: int = 0
    prompt_version: str | None = None
    provider: str | None = None


class IssueRead(BaseModel):
    code: str
    severity: str
    detail: str


class DraftSceneRead(BaseModel):
    title: str
    direction: str


class DraftRead(BaseModel):
    premise: str
    synopsis: str
    scenes: list[DraftSceneRead]
    script: str


class GenerateEpisodeOut(BaseModel):
    episode: EpisodeRead
    draft: DraftRead
    evaluation_status: str
    issues: list[IssueRead]
    prompt_version: str
    provider: str
    model: str
    canon_used: list[str]
    memories_used: list[str]
    resolved_threads: list[str]


@router.post("/api/series/{series_id}/generate-episode", response_model=GenerateEpisodeOut)
def generate_episode_endpoint(
    series_id: int, payload: GenerateEpisodeIn, db: Session = Depends(get_db)
) -> GenerateEpisodeOut:
    series = _series_or_404(db, series_id)
    if series.status != SeriesStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="series is ended; no new episodes",
        )
    creator = db.get(Creator, series.creator_id)
    if creator is None or not creator.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="creator is missing or inactive",
        )
    try:
        result: GenerationResult = generate_episode(
            db,
            series,
            creator,
            prompt_version=payload.prompt_version,
            provider_name=payload.provider,
            variant=payload.variant,
        )
    except EpisodeBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "draft blocked by evaluation; not persisted",
                "issues": [
                    {"code": i.code, "severity": i.severity.value, "detail": i.detail}
                    for i in exc.evaluation.issues
                ],
            },
        )
    except ParseError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown prompt version: {exc}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    draft = DraftRead(
        premise=result.draft.premise,
        synopsis=result.draft.synopsis,
        scenes=[DraftSceneRead.model_validate(s.model_dump()) for s in result.draft.scenes],
        script=result.draft.script,
    )
    return GenerateEpisodeOut(
        episode=EpisodeRead.model_validate(result.episode),
        draft=draft,
        evaluation_status=result.evaluation.status,
        issues=[
            IssueRead(code=i.code, severity=i.severity.value, detail=i.detail)
            for i in result.evaluation.issues
        ],
        prompt_version=result.prompt_version,
        provider=result.provider,
        model=result.model,
        canon_used=result.canon_used,
        memories_used=result.memories_used,
        resolved_threads=result.resolved_threads,
    )
