from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.calculadora import router as calculadora_router

app = FastAPI(
    title="Simulador IBS/CBS - Backend",
    description="Proxy para a Calculadora RTC da Reforma Tributária",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(calculadora_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "Simulador IBS/CBS Backend"}
