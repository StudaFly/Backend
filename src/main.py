from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="StudaFly API",
    description="Prépare ton départ à l'étranger, sereinement.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:19006"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"message": "Welcome to StudaFly API"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "0.1.0"}
