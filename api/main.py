from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from .endpoints import router as api_router
from ..core.config import settings

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="算力网络多智能体协同调度系统 API"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter()
app.include_router(api_router, prefix="/api")

@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.app_name} API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}