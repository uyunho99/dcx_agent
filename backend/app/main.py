from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import (
    sessions,
    keywords,
    crawling,
    preprocessing,
    labeling,
    training,
    clustering,
    embedding,
    personas,
    chat,
    search,
)

app = FastAPI(title="DCX Pipeline API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(keywords.router)
app.include_router(crawling.router)
app.include_router(preprocessing.router)
app.include_router(labeling.router)
app.include_router(training.router)
app.include_router(clustering.router)
app.include_router(embedding.router)
app.include_router(personas.router)
app.include_router(chat.router)
app.include_router(search.router)


@app.get("/health")
def health():
    return {"status": "ok"}
