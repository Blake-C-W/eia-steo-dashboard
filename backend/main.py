from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.services import connection
from backend.routers import api


@asynccontextmanager
async def lifespan(app: FastAPI):
    connection.get_connection()
    yield
    connection.close_connection()


app = FastAPI(title="EIA Forecast Accuracy Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite's default dev server port
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}