from pydantic import BaseModel
from typing import Optional, List, Any


class ImpostoSeletivoInput(BaseModel):
    cst: str
    baseCalculo: float
    cClassTrib: str
    unidade: str
    quantidade: float
    impostoInformado: float = 0


class TributacaoRegularInput(BaseModel):
    cst: str
    cClassTrib: str


class ItemInput(BaseModel):
    numero: int
    ncm: str
    nbs: Optional[str] = None
    quantidade: float
    unidade: str
    cst: str
    baseCalculo: float
    cClassTrib: str
    descricao: Optional[str] = None  # usado para enriquecer a simulação
    tributacaoRegular: Optional[TributacaoRegularInput] = None
    impostoSeletivo: Optional[ImpostoSeletivoInput] = None


class TributosAtuais(BaseModel):
    """Impostos extraídos do XML da NF-e — base para a simulação de transição."""
    vICMS:    float = 0  # ICMS próprio
    vST:      float = 0  # ICMS Substituição Tributária
    vIPI:     float = 0
    vPIS:     float = 0
    vCOFINS:  float = 0
    vISS:     float = 0  # ISS (para NFS-e / serviços)


class NotaFiscalInput(BaseModel):
    id: str = ""
    versao: str = "1.0.0"
    dataHoraEmissao: str
    municipio: int
    uf: str
    itens: List[ItemInput]
    tributosAtuais: Optional[TributosAtuais] = None  # não enviado à API externa


class CalculoResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None


class GerarXmlRequest(BaseModel):
    resultado: Any
