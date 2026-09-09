from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.db import Base, engine
from backend.routes import router


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.app_env in {"development", "test"}:
        Base.metadata.create_all(engine)
    yield


app = FastAPI(title="12345派单训练系统", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
