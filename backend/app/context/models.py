"""Stage 0 project context and its stable choice codes."""

from enum import Enum
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field, field_validator, model_validator


class TaskMode(str, Enum):
    metric = "metric"
    explore = "explore"


class PersonaDimension(str, Enum):
    social = "social"
    taste = "taste"
    movement = "movement"
    bio = "bio"


class KeyMetric(BaseModel):
    name: str = Field(min_length=1)
    source: str = ""
    item: str = ""

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value):
        if not value.strip():
            raise ValueError("지표명을 입력하세요")
        # Preserve historical metric text for byte-identical Markdown output.
        return value


class PersonaSeed(BaseModel):
    text: str = Field(min_length=1, max_length=40)
    dimension: PersonaDimension | None = None

    @field_validator("text", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class PersonaSeeds(BaseModel):
    items: list[PersonaSeed] = Field(default_factory=list, max_length=20)
    exploreBeyond: bool = True


class ProjectType(str, Enum):
    branding = "branding"
    new = "new"
    renewal = "renewal"
    ux = "ux"


class AnalysisGoal(str, Enum):
    needs = "needs"
    marketing = "marketing"
    concept = "concept"
    segment = "segment"


class Price(str, Enum):
    premium = "premium"
    value = "value"


class Market(str, Enum):
    leader = "leader"
    challenger = "challenger"
    new = "new"


class Channel(str, Enum):
    naver_cafe = "naver_cafe"
    naver_blog = "naver_blog"
    youtube = "youtube"
    ppomppu = "ppomppu"
    clien = "clien"
    fixture = "fixture"


class CategorySource(str, Enum):
    shopping = "shopping"
    llm_estimate = "llm_estimate"
    user = "user"


class Household(str, Enum):
    single = "single"
    newlywed = "newlywed"
    infant = "infant"
    school = "school"
    senior_cohab = "senior_cohab"


class LifeStage(str, Enum):
    student = "student"
    early_career = "early_career"
    parenting = "parenting"
    empty_nest = "empty_nest"
    retired = "retired"


class FutureCustomerChoice(str, Enum):
    competitor_users = "competitor_users"
    watchers = "watchers"
    churned = "churned"
    adjacent_needs = "adjacent_needs"


class AlignmentSource(str, Enum):
    constraints = "constraints"
    analysisGoal = "analysisGoal"
    positioning = "positioning"


Choice = TypeVar("Choice", bound=Enum)


class ChoiceWithNote(BaseModel, Generic[Choice]):
    choice: Choice
    note: str = ""


class ResearchQuestion(BaseModel):
    text: str
    template: str | None = None


class Positioning(BaseModel):
    price: Price | None = None
    market: Market | None = None
    priceText: str = Field(default="", max_length=40)
    marketText: str = Field(default="", max_length=40)

    @field_validator("price", "market", mode="before")
    @classmethod
    def blank_choice(cls, value):
        return None if value == "" else value

    @field_validator("priceText", "marketText", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def exclusive_axes(self):
        if (self.price is not None and self.priceText) or (self.market is not None and self.marketText):
            raise ValueError("포지셔닝은 축마다 기본 선택지 또는 직접 입력 하나만 선택하세요")
        return self


class ProductCategory(BaseModel):
    l1: str
    l2: str | None = None
    l3: str | None = None
    source: CategorySource


class TargetScope(BaseModel):
    ageRanges: list[str] = Field(default_factory=list)
    genders: list[str] = Field(default_factory=list)
    households: list[Household] = Field(default_factory=list)
    lifeStages: list[LifeStage] = Field(default_factory=list)
    note: str = ""


class FutureCustomer(BaseModel):
    choices: list[FutureCustomerChoice] = Field(default_factory=list)
    note: str = ""


class AlignmentWarning(BaseModel):
    source: AlignmentSource
    item: str
    reason: str


class ProjectContext(BaseModel):
    bk: str
    oneLiner: str
    researchQuestion: ResearchQuestion
    projectType: ChoiceWithNote[ProjectType]
    taskMode: TaskMode | None = None
    analysisGoal: ChoiceWithNote[AnalysisGoal] | None = None
    keyMetrics: list[KeyMetric] = Field(default_factory=list)
    constraints: list[str]
    positioning: Positioning = Field(default_factory=Positioning)
    personaSeeds: PersonaSeeds | None = None
    channels: list[Channel] = Field(min_length=1)
    knownInsights: list[str] = Field(default_factory=list)
    productCategory: ProductCategory
    targetScope: TargetScope | None = None
    futureCustomer: FutureCustomer | None = None
    schemaVersion: Literal[1] = 1

    @field_validator("keyMetrics", mode="before")
    @classmethod
    def legacy_metrics(cls, value):
        if isinstance(value, list):
            return [{"name": item} if isinstance(item, str) else item for item in value]
        return value

    @field_validator("analysisGoal", mode="before")
    @classmethod
    def empty_goal(cls, value):
        if isinstance(value, dict) and value.get("choice") == "":
            return None
        return value

    @model_validator(mode="after")
    def task_requirements(self):
        if self.taskMode in (None, TaskMode.metric) and not self.keyMetrics:
            raise ValueError("지표를 하나 이상 추가하세요.")
        if self.taskMode is None:
            if self.analysisGoal is None:
                raise ValueError("분석 목적을 선택하세요")
            if self.positioning.price is None or self.positioning.market is None:
                raise ValueError("가격 · 시장 포지셔닝을 선택하세요")
        return self
