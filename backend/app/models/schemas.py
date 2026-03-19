from pydantic import BaseModel


class CrawlRequest(BaseModel):
    sid: str = "s_unknown"
    bk: str = ""
    keywords: list[str] = []
    target: int = 50000
    dateFrom: str = ""
    dateTo: str = ""
    cafes: str | list = ""
    excludeCafes: str | list = ""
    adFilter: str | list = ""


class PreprocessRequest(BaseModel):
    sid: str = "s_unknown"
    extraFilter: str = ""
    excludeCafes: list[str] = []


class TrainRequest(BaseModel):
    sid: str = "s_unknown"
    bk: str = ""
    problemDef: str = ""


class ClusterRequest(BaseModel):
    sid: str = "s_unknown"
    num_clusters: int = 0


class ClusterRefineRequest(BaseModel):
    sid: str = "s_unknown"
    bk: str = ""
    keepClusters: str | list = ""
    mergeClusters: str | list = ""


class EmbedRequest(BaseModel):
    sid: str = "s_unknown"


class PersonaRequest(BaseModel):
    sid: str = "s_unknown"
    bk: str = ""
    problemDef: str = ""


class SessionSaveRequest(BaseModel):
    sid: str = "s_unknown"
    data: dict = {}


class SearchRequest(BaseModel):
    sid: str = "s0"
    query: str = ""
    top_k: int = 10


class ChatRequest(BaseModel):
    sid: str = "s0"
    query: str = ""
    pipeline_context: str = ""


class InsightChatRequest(BaseModel):
    sid: str = "s0"
    query: str = ""
    bk: str = ""


class KeywordGenRequest(BaseModel):
    sid: str = ""
    bk: str = ""
    problemDef: str = ""
    existingKeywords: list[str] = []
    round: int = 1
    ages: list[str] = []
    ageRange: list[str] = []
    gens: list[str] = []
