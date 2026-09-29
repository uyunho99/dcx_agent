"""Version-aware crawl API with the shared v2 error envelope."""
from datetime import date, timedelta
from fastapi import APIRouter
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, AliasChoices, model_validator
from app.context.store import StoreError
from app.crawl import control
from app.crawl.filters import DEFAULT_AD_WORDS, DEFAULT_EXCLUDE_SOURCES


class CrawlRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def wrapped(request):
            try:
                return await handler(request)
            except StoreError as exc:
                return JSONResponse(status_code=exc.status, content={'status': 'error', 'error': {'kind': exc.kind, 'message': str(exc)}})
            except RequestValidationError:
                return JSONResponse(status_code=422, content={'status': 'error', 'error': {'kind': 'validation', 'message': 'Invalid crawl request'}})
            except OSError:
                return JSONResponse(status_code=500, content={'status': 'error', 'error': {'kind': 'storage', 'message': 'Crawl storage or worker operation failed'}})
        return wrapped


router = APIRouter(prefix='/crawl', route_class=CrawlRoute)


class Limits(BaseModel):
    model_config = ConfigDict(extra='forbid')
    concurrency: int = Field(default=4, ge=1, le=64)
    min_interval_s: float = Field(default=0, ge=0)
    max_per_keyword: int = Field(default=1000, ge=1)
    per_minute: float = Field(default=60, gt=0)


class Youtube(BaseModel):
    model_config = ConfigDict(extra='forbid')
    videos_per_keyword: int = Field(default=20, ge=1)
    max_comments: int = Field(default=500, ge=0)


class Config(BaseModel):
    model_config = ConfigDict(extra='forbid')
    channels: list[str] = Field(validation_alias=AliasChoices('channels', 'sources'), min_length=1)
    dateFrom: date | None = Field(default_factory=lambda: date.today() - timedelta(days=365))
    dateTo: date | None = Field(default_factory=date.today)
    adWords: list[str] = Field(default_factory=lambda: DEFAULT_AD_WORDS.copy())
    excludeSources: list[str] = Field(default_factory=lambda: DEFAULT_EXCLUDE_SOURCES.copy())
    includeSources: list[str] = Field(default_factory=list)
    product_name_filter: bool = Field(default=False, validation_alias=AliasChoices('product_name_filter', 'productNameFilter'))
    perChannel: dict[str, Limits] = Field(default_factory=dict)
    youtube: Youtube = Field(default_factory=Youtube)
    target_total: int | None = Field(default=None, ge=1)
    @model_validator(mode='after')
    def dates(self):
        if self.dateFrom and self.dateTo and self.dateFrom > self.dateTo:
            raise ValueError('Invalid date range')
        if set(self.perChannel) - set(self.channels):
            raise ValueError('Unknown channel limits')
        return self


class Gate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    exclusions: list[str] = Field(validation_alias=AliasChoices('exclusions', 'gateExclusions'))


class Detail(BaseModel):
    model_config = ConfigDict(extra='forbid')
    snapshot_id: str = Field(min_length=1, validation_alias=AliasChoices('snapshot_id', 'snapshotId'))


@router.put('/{sid}/config')
def config(sid: str, body: Config, version: str | None = None):
    return control.save_config(sid, body.model_dump(mode='json'), version)


@router.post('/{sid}/list')
def start_list(sid: str, mode: str | None = None, version: str | None = None):
    return control.start_list(sid, mode, version)


@router.put('/{sid}/gate')
def gate(sid: str, body: Gate, version: str | None = None):
    return control.save_gate(sid, body.exclusions, version)


@router.post('/{sid}/detail')
def detail(sid: str, body: Detail, version: str | None = None):
    return control.start_detail(sid, body.snapshot_id, version)


@router.get('/{sid}/status')
def status(sid: str):
    return control.status(sid)


@router.post('/{sid}/resume')
def resume(sid: str, version: str | None = None):
    return control.resume(sid, version)


@router.post('/{sid}/stop')
def stop(sid: str, version: str | None = None):
    return control.stop(sid, version)
