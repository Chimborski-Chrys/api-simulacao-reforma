"""
Simulação da Transição Tributária - IBS/CBS/IS (2026-2033)
Baseado na LC 214/2025 e projeções da Reforma Tributária.

Alíquotas de referência projetadas:
  CBS: 8,8%   IBS: 17,7% (total UF + Município)   IS: variável por NCM

Impostos que coexistem com o IVA durante a transição:
  2026       : IBS+CBS (piloto 1%) + ICMS 100% + PIS/COFINS 100% + IPI 100%
  2027-2028  : IBS+CBS + ICMS 100% (PIS/COFINS e IPI extintos)
  2029       : IBS+CBS + ICMS 90%
  2030       : IBS+CBS + ICMS 80%
  2031       : IBS+CBS + ICMS 70%
  2032       : IBS+CBS + ICMS 60%
  2033       : IBS+CBS plenos (ICMS/ISS extintos)
"""

from typing import Optional

# ── Categorias do Imposto Seletivo (IS) ─────────────────────────────────────
IS_CATEGORIES = [
    {"prefixes": ["2401", "2402", "2403"],                                "rate": 1.00, "desc": "Produtos fumígenos (tabaco/cigarro)"},
    {"prefixes": ["2203", "2204", "2205", "2206", "2207", "2208"],        "rate": 0.20, "desc": "Bebidas alcoólicas"},
    {"prefixes": ["2202"],                                                 "rate": 0.20, "desc": "Bebidas açucaradas / energéticas"},
    {"prefixes": ["8701","8702","8703","8704","8705","8706","8707","8708","8711"], "rate": 0.07, "desc": "Veículos automotores"},
    {"prefixes": ["8901","8902","8903","8904","8905","8906","8907","8908"],"rate": 0.03, "desc": "Embarcações"},
    {"prefixes": ["8801","8802","8803","8804","8805"],                     "rate": 0.03, "desc": "Aeronaves"},
    {"prefixes": ["9301","9302","9303","9304","9305","9306"],              "rate": 0.25, "desc": "Armas e munições"},
    {"prefixes": ["2709","2710","2711"],                                   "rate": 0.01, "desc": "Minerais / combustíveis fósseis"},
]

# ── Cronograma de Alíquotas 2026-2033 ────────────────────────────────────────
#
# icms_fator      : fração do ICMS original que ainda vigora
# pisCofins_fator : 1.0 em 2026 (ainda vigente), 0.0 de 2027 em diante (extintos)
# ipi_fator       : idem PIS/COFINS
#
TRANSITION_YEARS = [
    {
        "ano": 2026,
        "fase": "Fase Piloto",
        "descricao": "IVA simbólico (1%) + ICMS + PIS/COFINS + IPI plenos",
        "cbs": 0.009, "ibs": 0.001,
        "aplica_is": False,
        "icms_fator": 1.0, "pisCofins_fator": 1.0, "ipi_fator": 1.0,
        "fonte": "api",
    },
    {
        "ano": 2027,
        "fase": "Transição Inicial",
        "descricao": "CBS definitiva + ICMS pleno — PIS/COFINS/IPI extintos",
        "cbs": 0.088, "ibs": 0.001,
        "aplica_is": True,
        "icms_fator": 1.0, "pisCofins_fator": 0.0, "ipi_fator": 0.0,
        "fonte": "simulado",
    },
    {
        "ano": 2028,
        "fase": "Transição Inicial",
        "descricao": "CBS definitiva + ICMS pleno — PIS/COFINS/IPI extintos",
        "cbs": 0.088, "ibs": 0.002,
        "aplica_is": True,
        "icms_fator": 1.0, "pisCofins_fator": 0.0, "ipi_fator": 0.0,
        "fonte": "simulado",
    },
    {
        "ano": 2029,
        "fase": "Substituição Gradual (10%)",
        "descricao": "IBS 10% da alíquota cheia — ICMS cai para 90%",
        "cbs": 0.088, "ibs": 0.0177,
        "aplica_is": True,
        "icms_fator": 0.9, "pisCofins_fator": 0.0, "ipi_fator": 0.0,
        "fonte": "simulado",
    },
    {
        "ano": 2030,
        "fase": "Substituição Gradual (20%)",
        "descricao": "IBS 20% da alíquota cheia — ICMS cai para 80%",
        "cbs": 0.088, "ibs": 0.0354,
        "aplica_is": True,
        "icms_fator": 0.8, "pisCofins_fator": 0.0, "ipi_fator": 0.0,
        "fonte": "simulado",
    },
    {
        "ano": 2031,
        "fase": "Substituição Gradual (30%)",
        "descricao": "IBS 30% da alíquota cheia — ICMS cai para 70%",
        "cbs": 0.088, "ibs": 0.0531,
        "aplica_is": True,
        "icms_fator": 0.7, "pisCofins_fator": 0.0, "ipi_fator": 0.0,
        "fonte": "simulado",
    },
    {
        "ano": 2032,
        "fase": "Substituição Gradual (40%)",
        "descricao": "IBS 40% da alíquota cheia — ICMS cai para 60%",
        "cbs": 0.088, "ibs": 0.0708,
        "aplica_is": True,
        "icms_fator": 0.6, "pisCofins_fator": 0.0, "ipi_fator": 0.0,
        "fonte": "simulado",
    },
    {
        "ano": 2033,
        "fase": "Alíquota Cheia",
        "descricao": "Plena vigência do IVA Dual — ICMS e ISS extintos",
        "cbs": 0.088, "ibs": 0.177,
        "aplica_is": True,
        "icms_fator": 0.0, "pisCofins_fator": 0.0, "ipi_fator": 0.0,
        "fonte": "simulado",
    },
]


def detectar_is(ncm: str) -> Optional[dict]:
    prefix4 = (ncm or "").replace(".", "")[:4]
    for cat in IS_CATEGORIES:
        if prefix4 in cat["prefixes"]:
            return {"rate": cat["rate"], "desc": cat["desc"]}
    return None


def _extrair_item_2026(obj: dict, itens_input: list) -> dict:
    nobj = obj.get("nObj", 1)
    trib = obj.get("tribCalc", {})
    ibscbs = trib.get("IBSCBS", {})
    gibscbs = ibscbs.get("gIBSCBS", {})

    vBC  = float(gibscbs.get("vBC", 0))
    vIBS = float(gibscbs.get("vIBS", 0))
    gCBS = gibscbs.get("gCBS", {})
    vCBS = float(gCBS.get("vCBS", 0))
    pCBS = float(gCBS.get("pCBS", 0))
    pIBSUF  = float(gibscbs.get("gIBSUF", {}).get("pIBSUF", 0))
    pIBSMun = float(gibscbs.get("gIBSMun", {}).get("pIBSMun", 0))

    is_trib = trib.get("IS", {})
    vIS = float(is_trib.get("vIS", 0))

    inp = next((i for i in itens_input if i.get("numero") == nobj), {})

    return {
        "numero":      nobj,
        "ncm":         inp.get("ncm", ""),
        "descricao":   inp.get("descricao", f"Item {nobj}"),
        "baseCalculo": vBC,
        "cbs":         round(vCBS, 2),
        "ibs":         round(vIBS, 2),
        "is":          round(vIS, 2),
        "isInfo":      None,
        "aliqCbs":     pCBS,
        "aliqIbs":     pIBSUF + pIBSMun,
        "total":       round(vCBS + vIBS + vIS, 2),  # apenas IVA — legados somados no total do ano
    }


def calcular_transicao(
    resultado_api: dict,
    itens_input: list,
    tributos_atuais: Optional[dict] = None,
) -> list:
    """
    Builds annual projections 2026-2033.

    tributos_atuais (optional): legacy tax values extracted from NF-e XML
      keys: vICMS, vST, vIPI, vPIS, vCOFINS, vISS
    """
    ta = tributos_atuais or {}
    # ICMS total = ICMS próprio + ICMS-ST + ISS (treated the same way)
    v_icms      = float(ta.get("vICMS", 0)) + float(ta.get("vST", 0)) + float(ta.get("vISS", 0))
    v_pisCofins = float(ta.get("vPIS", 0))  + float(ta.get("vCOFINS", 0))
    v_ipi       = float(ta.get("vIPI", 0))

    objetos = resultado_api.get("objetos", [])
    anos = []

    for cfg in TRANSITION_YEARS:
        ano = cfg["ano"]

        # ── IVA per-item (IBS + CBS + IS) ────────────────────────────────
        if ano == 2026:
            itens_ano = [_extrair_item_2026(obj, itens_input) for obj in objetos]
        else:
            cbs_rate  = cfg["cbs"]
            ibs_rate  = cfg["ibs"]
            aplica_is = cfg["aplica_is"]
            itens_ano = []
            for inp in itens_input:
                bc    = inp.get("baseCalculo", 0)
                ncm   = inp.get("ncm", "")
                nobj  = inp.get("numero", 1)
                vCBS  = round(bc * cbs_rate, 2)
                vIBS  = round(bc * ibs_rate, 2)
                is_info = detectar_is(ncm) if aplica_is else None
                vIS   = round(bc * is_info["rate"], 2) if is_info else 0
                itens_ano.append({
                    "numero":      nobj,
                    "ncm":         ncm,
                    "descricao":   inp.get("descricao", f"Item {nobj}"),
                    "baseCalculo": bc,
                    "cbs":  vCBS, "ibs":  vIBS, "is":   vIS,
                    "isInfo": is_info,
                    "aliqCbs": cbs_rate * 100,
                    "aliqIbs": ibs_rate * 100,
                    "total": round(vCBS + vIBS + vIS, 2),
                })

        # ── Legacy taxes residual for this year ───────────────────────────
        icms_residual      = round(v_icms      * cfg["icms_fator"],      2)
        pisCofins_residual = round(v_pisCofins * cfg["pisCofins_fator"],  2)
        ipi_residual       = round(v_ipi       * cfg["ipi_fator"],        2)
        tributos_anteriores = round(icms_residual + pisCofins_residual + ipi_residual, 2)

        # ── Year totals ───────────────────────────────────────────────────
        total_cbs = round(sum(i["cbs"] for i in itens_ano), 2)
        total_ibs = round(sum(i["ibs"] for i in itens_ano), 2)
        total_is  = round(sum(i["is"]  for i in itens_ano), 2)
        total_iva = round(total_cbs + total_ibs + total_is, 2)
        total_geral = round(total_iva + tributos_anteriores, 2)

        anos.append({
            "ano":        ano,
            "fase":       cfg["fase"],
            "descricao":  cfg["descricao"],
            "aliqCbs":    cfg["cbs"] * 100,
            "aliqIbs":    cfg["ibs"] * 100,
            "aplicaIS":   cfg["aplica_is"],
            "fonte":      cfg["fonte"],
            "itens":      itens_ano,
            "total": {
                "cbs":               total_cbs,
                "ibs":               total_ibs,
                "iva":               total_iva,       # IBS + CBS + IS
                "is":                total_is,
                "icms":              icms_residual,
                "pisCofins":         pisCofins_residual,
                "ipi":               ipi_residual,
                "tributosAnteriores": tributos_anteriores,
                "geral":             total_geral,
            },
        })

    return anos
