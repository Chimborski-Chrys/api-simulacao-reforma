import os
import httpx
from typing import Any

# Online API oficial (Receita Federal / SEFAZ)
ONLINE_URL = "https://consumo.tributos.gov.br/servico/calcular-tributos-consumo"

# API local (localhost:8080) — usada como fallback se a online falhar
LOCAL_URL = "http://localhost:8080"

# Pode ser sobrescrito via variável de ambiente CALCULADORA_URL
BASE_URL = os.getenv("CALCULADORA_URL", ONLINE_URL)

_HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}


async def _post(url: str, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload, headers=_HEADERS)
        resp.raise_for_status()
        return resp.json()


async def calcular_tributos(payload: dict) -> dict:
    """
    Calls the IBS/CBS calculator API.
    Tries BASE_URL (online by default); falls back to LOCAL_URL if unavailable.
    """
    urls = [BASE_URL]
    if BASE_URL != LOCAL_URL:
        urls.append(LOCAL_URL)

    last_error: Exception = httpx.ConnectError("Calculadora indisponível")
    for base in urls:
        try:
            return await _post(
                f"{base}/api/calculadora/regime-geral", payload
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            last_error = exc
            continue

    raise last_error


async def buscar_situacoes_tributarias(data: str) -> list:
    """
    Fetches the list of CST codes (situações tributárias) for CBS/IBS from the
    dados-abertos endpoint for the given date (YYYY-MM-DD).
    Falls back to local API if online is unavailable.
    """
    urls = [BASE_URL]
    if BASE_URL != LOCAL_URL:
        urls.append(LOCAL_URL)

    last_error: Exception = httpx.ConnectError("Calculadora indisponível")
    for base in urls:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{base}/api/calculadora/dados-abertos/situacoes-tributarias/cbs-ibs",
                    params={"data": data},
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                return resp.json()
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            last_error = exc
            continue

    raise last_error


async def buscar_classificacoes_tributarias(cst_id: int, data: str) -> list:
    """
    Fetches cClassTrib classifications for a given CST id and date (YYYY-MM-DD).
    Endpoint: /api/calculadora/dados-abertos/classificacoes-tributarias/{cst_id}
    """
    urls = [BASE_URL]
    if BASE_URL != LOCAL_URL:
        urls.append(LOCAL_URL)

    last_error: Exception = httpx.ConnectError("Calculadora indisponível")
    for base in urls:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{base}/api/calculadora/dados-abertos/classificacoes-tributarias/{cst_id}",
                    params={"data": data},
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                return resp.json()
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            last_error = exc
            continue

    raise last_error


async def gerar_xml(payload: dict) -> Any:
    urls = [BASE_URL]
    if BASE_URL != LOCAL_URL:
        urls.append(LOCAL_URL)

    last_error: Exception = httpx.ConnectError("Calculadora indisponível")
    for base in urls:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{base}/api/calculadora/xml/generate",
                    json=payload,
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                if "xml" in content_type:
                    return resp.text
                return resp.json()
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            last_error = exc
            continue

    raise last_error
