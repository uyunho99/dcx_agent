from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    sessions,
    context,
    integrations,
    keywords,
    keywords_v2,
    crawl_v2,
    preprocessing,
    prep,
    labeling,
    labeling_v2,
    training,
    training_v2,
    clustering,
    segment,
    stage8,
    embedding,
    personas,
    chat,
    search,
    known,
)

@asynccontextmanager
async def lifespan(app):
    from app.keywords.rounds import recover_interrupted
    recover_interrupted()
    yield


app = FastAPI(title="DCX Pipeline API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(integrations.router)
app.include_router(context.router)
app.include_router(keywords.router)
app.include_router(keywords_v2.router)
app.include_router(crawl_v2.router)
app.include_router(preprocessing.router)
app.include_router(prep.router)
app.include_router(labeling.router)
app.include_router(labeling_v2.router)
app.include_router(training.router)
app.include_router(training_v2.router)
app.include_router(clustering.router)
app.include_router(segment.router)
app.include_router(stage8.router)
app.include_router(embedding.router)
app.include_router(personas.router)
app.include_router(chat.router)
app.include_router(search.router)
app.include_router(known.router)


@app.get("/health")
def health():
    return {"status": "ok"}
