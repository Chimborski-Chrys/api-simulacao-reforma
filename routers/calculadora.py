from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from models.schemas import NotaFiscalInput, CalculoResponse, GerarXmlRequest
from services.calculadora_service import calcular_tributos, gerar_xml, buscar_situacoes_tributarias, buscar_classificacoes_tributarias, ONLINE_URL, BASE_URL
from services.transicao_service import calcular_transicao
from services.projecao_rtc_service import calcular_projecao_rtc
from datetime import datetime, timezone, timedelta
import httpx

router = APIRouter(prefix="/api", tags=["calculadora"])


def _data_atual_br() -> str:
    """Returns current date/time in Brazil timezone (UTC-3) in ISO format."""
    br_tz = timezone(timedelta(hours=-3))
    return datetime.now(br_tz).strftime("%Y-%m-%dT%H:%M:%S-03:00")


def _base_payload(nota_dict: dict) -> dict:
    """Returns payload without 'itens', with dataHoraEmissao = current date."""
    base = {k: v for k, v in nota_dict.items() if k != "itens"}
    base["dataHoraEmissao"] = _data_atual_br()  # API uses current date for rate lookup
    return base


def _aggregate_total(objetos: list) -> dict:
    """Sums IBS/CBS/IS values across all objetos to build a combined total."""
    total_bc = total_ibs = total_cbs = total_is = 0.0

    for obj in objetos:
        trib = obj.get("tribCalc", {})

        ibscbs = trib.get("IBSCBS", {})
        gibscbs = ibscbs.get("gIBSCBS", {})
        total_bc  += float(gibscbs.get("vBC", 0) or 0)
        total_ibs += float(gibscbs.get("vIBS", 0) or 0)
        total_cbs += float(gibscbs.get("gCBS", {}).get("vCBS", 0) or 0)

        is_trib = trib.get("IS", {})
        total_is += float(is_trib.get("vIS", 0) or 0)

    return {
        "tribCalc": {
            "IBSCBSTot": {
                "vBCIBSCBS": f"{total_bc:.2f}",
                "gIBS": {"vIBS": f"{total_ibs:.2f}"},
                "gCBS": {"vCBS": f"{total_cbs:.2f}"},
                "gIS":  {"vIS":  f"{total_is:.2f}"},
            }
        }
    }


async def _calcular_por_item(base: dict, itens: list) -> dict:
    """
    Calls the calculator API once per item (the endpoint rejects duplicate
    'numero' values within a single request).

    Returns a combined response in the same shape as a single multi-item call:
    { "objetos": [...], "total": { ... } }
    """
    all_objetos = []

    for item_dict in itens:
        payload = {**base, "itens": [item_dict]}
        result = await calcular_tributos(payload)
        all_objetos.extend(result.get("objetos", []))

    return {
        "objetos": all_objetos,
        "total": _aggregate_total(all_objetos),
    }


@router.get("/situacoes-tributarias")
async def situacoes_tributarias():
    """Returns the list of CST codes (situações tributárias) for CBS/IBS, using today's date."""
    try:
        today = _data_atual_br()[:10]  # "YYYY-MM-DD"
        return await buscar_situacoes_tributarias(today)
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Erro ao buscar situações tributárias: {e.response.text}",
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Calculadora RTC indisponível. Verifique a conexão.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/classificacoes-tributarias/{cst_id}")
async def classificacoes_tributarias(cst_id: int):
    """Returns cClassTrib classifications for the given CST id, using today's date."""
    try:
        today = _data_atual_br()[:10]  # "YYYY-MM-DD"
        return await buscar_classificacoes_tributarias(cst_id, today)
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Erro ao buscar classificações: {e.response.text}",
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Calculadora RTC indisponível. Verifique a conexão.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calcular", response_model=CalculoResponse)
async def calcular(nota: NotaFiscalInput):
    try:
        # Build payload dict — strip fields not accepted by the external API
        nota_dict = nota.model_dump(exclude_none=True)
        nota_dict.pop("tributosAtuais", None)  # internal only, not sent to API
        for item in nota_dict.get("itens", []):
            item.pop("descricao", None)
            item.pop("nbs", None)

        base = _base_payload(nota_dict)
        itens = nota_dict.get("itens", [])

        # One API call per item — avoids "item duplicado" rejection
        resultado_api = await _calcular_por_item(base, itens)

        # Enrich with descricao for transition simulation display
        itens_enriquecidos = [
            i.model_dump(exclude_none=True) for i in nota.itens
        ]

        # Legacy taxes from XML for transition calculation
        tributos_atuais = (
            nota.tributosAtuais.model_dump() if nota.tributosAtuais else None
        )

        transicao = calcular_transicao(resultado_api, itens_enriquecidos, tributos_atuais)

        return CalculoResponse(
            success=True,
            data={
                "resultado2026": resultado_api,
                "transicao": transicao,
                "fonte": "online" if BASE_URL == ONLINE_URL else "local",
            },
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Erro na calculadora: {e.response.text}",
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Calculadora RTC indisponível. "
                "Verifique a conexão ou inicie a API local em localhost:8080."
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calcular-rtc", response_model=CalculoResponse)
async def calcular_rtc(nota: NotaFiscalInput):
    """
    Calls the RTC calculator for EACH year 2026-2033 in parallel (8 requests).
    Items are renumbered sequentially so the API accepts them in a single request per year.
    Legacy taxes (ICMS reduction schedule, PIS/COFINS/IPI extinction) are still computed
    from the same LC 214/2025 transition factors as the internal projection.
    """
    try:
        nota_dict = nota.model_dump(exclude_none=True)
        nota_dict.pop("tributosAtuais", None)
        for item in nota_dict.get("itens", []):
            item.pop("descricao", None)
            item.pop("nbs", None)

        base = _base_payload(nota_dict)

        # Renumber items sequentially: 1, 2, 3… (API requires unique incremental numero)
        itens_normalizados = [
            {**item, "numero": idx + 1}
            for idx, item in enumerate(nota_dict.get("itens", []))
        ]

        # Keep original items (with descricao/ncm) for display in ResultsPanel
        itens_input = [
            {**i.model_dump(exclude_none=True), "numero": idx + 1}
            for idx, i in enumerate(nota.itens)
        ]

        tributos_atuais = (
            nota.tributosAtuais.model_dump() if nota.tributosAtuais else None
        )

        # 8 parallel API calls — one per year
        transicao = await calcular_projecao_rtc(
            base, itens_normalizados, itens_input, tributos_atuais
        )

        # resultado2026 is already inside transicao[0]; expose it separately for compatibility
        resultado2026 = {"objetos": [], "total": {}}
        if transicao:
            first = transicao[0]
            resultado2026 = {
                "objetos": [
                    {
                        "nObj": it["numero"],
                        "tribCalc": {
                            "IBSCBS": {
                                "gIBSCBS": {
                                    "vBC":  str(it["baseCalculo"]),
                                    "vIBS": str(it["ibs"]),
                                    "gCBS": {"vCBS": str(it["cbs"]), "pCBS": str(it["aliqCbs"])},
                                }
                            },
                            "IS": {"vIS": str(it["is"])},
                        },
                    }
                    for it in first.get("itens", [])
                ],
                "total": {
                    "tribCalc": {
                        "IBSCBSTot": {
                            "vBCIBSCBS": str(sum(i["baseCalculo"] for i in first.get("itens", []))),
                            "gIBS": {"vIBS": str(first["total"]["ibs"])},
                            "gCBS": {"vCBS": str(first["total"]["cbs"])},
                            "gIS":  {"vIS":  str(first["total"]["is"])},
                        }
                    }
                },
            }

        return CalculoResponse(
            success=True,
            data={
                "resultado2026": resultado2026,
                "transicao":     transicao,
                "fonte":         "online" if BASE_URL == ONLINE_URL else "local",
                "metodo":        "rtc",
            },
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Erro na calculadora RTC: {e.response.text}",
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Calculadora RTC indisponível. Verifique a conexão ou inicie a API local em localhost:8080.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gerar-xml")
async def gerar_xml_route(request: GerarXmlRequest):
    try:
        resultado = await gerar_xml(request.resultado)
        if isinstance(resultado, str):
            return PlainTextResponse(resultado, media_type="application/xml")
        return {"success": True, "data": resultado}
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Erro ao gerar XML: {e.response.text}",
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Calculadora RTC indisponível. Verifique se está rodando em localhost:8080.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
