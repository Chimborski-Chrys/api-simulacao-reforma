"""
Projeção de carga tributária 2026-2033 via API oficial da Calculadora RTC.

Estratégia:
  - Envia todos os itens em um único request por ano (itens renumerados 1, 2, 3…)
  - 8 chamadas em paralelo (asyncio.gather) → ~3-5s no total
  - Tributos legados (ICMS/PIS-COFINS/IPI) calculados pelos mesmos fatores de
    transição da LC 214/2025 usados na projeção interna (não há dados da API para isso)

Retorna lista no mesmo formato de transicao_service.calcular_transicao(), para que
ResultsPanel.vue possa exibir sem alterações.
"""

import asyncio
from typing import Optional

import httpx

from services.calculadora_service import BASE_URL, LOCAL_URL, _HEADERS
from services.transicao_service import TRANSITION_YEARS, detectar_is


async def _post_year(year: int, payload: dict) -> dict:
    """
    POST to the calculator for a specific year.
    Tries ONLINE_URL first, falls back to LOCAL_URL.
    """
    urls = [BASE_URL]
    if BASE_URL != LOCAL_URL:
        urls.append(LOCAL_URL)

    last_exc: Exception = httpx.ConnectError("Calculadora indisponível")
    for base in urls:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{base}/api/calculadora/regime-geral",
                    json=payload,
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                return resp.json()
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            last_exc = exc
            continue

    raise last_exc


def _extrair_itens_rtc(objetos: list, itens_input: list) -> list:
    """
    Formats API objects into the same per-item structure as transicao_service.
    nObj is matched to itens_input by index (both are renumbered 1, 2, 3…).
    """
    inp_by_num = {i.get("numero", idx + 1): i for idx, i in enumerate(itens_input)}

    result = []
    for obj in objetos:
        nobj = obj.get("nObj", 1)
        trib = obj.get("tribCalc", {})
        ibscbs = trib.get("IBSCBS", {})
        gibscbs = ibscbs.get("gIBSCBS", {})

        vBC   = float(gibscbs.get("vBC",  0) or 0)
        vIBS  = float(gibscbs.get("vIBS", 0) or 0)
        gCBS  = gibscbs.get("gCBS", {})
        vCBS  = float(gCBS.get("vCBS", 0) or 0)
        pCBS  = float(gCBS.get("pCBS", 0) or 0)
        pIBSUF  = float(gibscbs.get("gIBSUF",  {}).get("pIBSUF",  0) or 0)
        pIBSMun = float(gibscbs.get("gIBSMun", {}).get("pIBSMun", 0) or 0)

        is_trib = trib.get("IS", {})
        vIS = float(is_trib.get("vIS", 0) or 0)

        inp = inp_by_num.get(nobj, {})
        ncm = inp.get("ncm", "")
        is_info = detectar_is(ncm) if vIS > 0 else None

        result.append({
            "numero":      nobj,
            "ncm":         ncm,
            "descricao":   inp.get("descricao", f"Item {nobj}"),
            "baseCalculo": vBC,
            "cbs":         round(vCBS, 2),
            "ibs":         round(vIBS, 2),
            "is":          round(vIS, 2),
            "isInfo":      is_info,
            "aliqCbs":     pCBS,
            "aliqIbs":     pIBSUF + pIBSMun,
            "total":       round(vCBS + vIBS + vIS, 2),
        })
    return result


async def calcular_projecao_rtc(
    base_payload: dict,
    itens_normalizados: list,       # items already renumbered 1, 2, 3…
    itens_input: list,              # original items (for descricao, ncm)
    tributos_atuais: Optional[dict] = None,
) -> list:
    """
    Calls the RTC calculator for all years 2026-2033 in parallel.

    Args:
        base_payload: nota fields without 'itens' and with current date.
        itens_normalizados: items renumbered sequentially (numero = 1, 2, 3…).
        itens_input: original items list (for description/NCM lookup).
        tributos_atuais: legacy tax values from XML for transition calculation.

    Returns:
        List of year entries in the same format as transicao_service output.
    """
    ta = tributos_atuais or {}
    v_icms      = float(ta.get("vICMS", 0)) + float(ta.get("vST", 0)) + float(ta.get("vISS", 0))
    v_pisCofins = float(ta.get("vPIS", 0))  + float(ta.get("vCOFINS", 0))
    v_ipi       = float(ta.get("vIPI", 0))

    # Build one payload per year — only dataHoraEmissao changes
    async def _task(cfg: dict):
        year = cfg["ano"]
        payload = {
            **base_payload,
            "dataHoraEmissao": f"{year}-01-01T12:00:00-03:00",
            "itens": itens_normalizados,
        }
        resultado = await _post_year(year, payload)
        return cfg, resultado

    pairs = await asyncio.gather(
        *[_task(cfg) for cfg in TRANSITION_YEARS],
        return_exceptions=True,
    )

    anos = []
    for pair in pairs:
        if isinstance(pair, Exception):
            continue  # skip years where the API call failed

        cfg, resultado = pair
        itens_ano = _extrair_itens_rtc(resultado.get("objetos", []), itens_input)

        # Legacy taxes (ICMS reducing schedule, PIS/COFINS/IPI extinction)
        icms_residual      = round(v_icms      * cfg["icms_fator"],      2)
        pisCofins_residual = round(v_pisCofins * cfg["pisCofins_fator"],  2)
        ipi_residual       = round(v_ipi       * cfg["ipi_fator"],        2)
        tributos_anteriores = round(icms_residual + pisCofins_residual + ipi_residual, 2)

        total_cbs = round(sum(i["cbs"] for i in itens_ano), 2)
        total_ibs = round(sum(i["ibs"] for i in itens_ano), 2)
        total_is  = round(sum(i["is"]  for i in itens_ano), 2)
        total_iva = round(total_cbs + total_ibs + total_is, 2)
        total_bc  = sum(i["baseCalculo"] for i in itens_ano)

        # Effective rate = weighted average across all items
        aliq_cbs_ef = round((total_cbs / total_bc * 100) if total_bc else 0, 3)
        aliq_ibs_ef = round((total_ibs / total_bc * 100) if total_bc else 0, 3)

        anos.append({
            "ano":       cfg["ano"],
            "fase":      cfg["fase"],
            "descricao": cfg["descricao"],
            "aliqCbs":   aliq_cbs_ef,
            "aliqIbs":   aliq_ibs_ef,
            "aplicaIS":  cfg["aplica_is"],
            "fonte":     "api-rtc",
            "itens":     itens_ano,
            "total": {
                "cbs":               total_cbs,
                "ibs":               total_ibs,
                "iva":               total_iva,
                "is":                total_is,
                "icms":              icms_residual,
                "pisCofins":         pisCofins_residual,
                "ipi":               ipi_residual,
                "tributosAnteriores": tributos_anteriores,
                "geral":             round(total_iva + tributos_anteriores, 2),
            },
        })

    return anos
