"""Stage 0 project context and its stable choice codes."""

from enum import Enum
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field


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
    price: Price
    market: Market


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
    analysisGoal: ChoiceWithNote[AnalysisGoal]
    keyMetrics: list[str] = Field(min_length=1)
    constraints: list[str]
    positioning: Positioning
    channels: list[Channel] = Field(min_length=1)
    knownInsights: list[str] = Field(default_factory=list)
    productCategory: ProductCategory
    targetScope: TargetScope | None = None
    futureCustomer: FutureCustomer | None = None
    schemaVersion: Literal[1] = 1
