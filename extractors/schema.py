"""
GeoBIM Intelligence — Schema Pydantic v1.1.0
"""
from pydantic import BaseModel, Field
from typing import Optional, List


class Coordinates(BaseModel):
    lat: Optional[float] = None
    lng: Optional[float] = None
    crs: str = "EPSG:4326"
    format: str = "dms"
    source_verbatim: Optional[str] = None
    page: Optional[int] = None


class Falda(BaseModel):
    depth_m: Optional[float] = None
    absent: bool = False
    date: Optional[str] = None
    pages: List[int] = []
    source_verbatim: Optional[str] = None


class PermeabilityValue(BaseModel):
    value: Optional[float] = None
    unit: str = "m/s"


class SPTMeasure(BaseModel):
    prof: Optional[float] = Field(None, description="Profondita in metri dal p.c.")
    N1: Optional[int] = None
    N2: Optional[int] = None
    N3: Optional[int] = None
    Nspt: Optional[int] = None
    page: Optional[int] = None
    source_verbatim: Optional[str] = None


class PermeabilityMeasure(BaseModel):
    prof: Optional[float] = None
    permeability: Optional[PermeabilityValue] = None
    permeability_h: Optional[PermeabilityValue] = None
    permeability_v: Optional[PermeabilityValue] = None
    page: Optional[int] = None
    source_verbatim: Optional[str] = None


class Sondaggio(BaseModel):
    sondage_id: str = Field(..., description="Es: S01, S01BIS, S06R")
    sondage_type: str = Field(..., description="rotary_carotaggio | distruzione_di_nucleo")
    source_file: str = ""
    campaign_year: Optional[str] = None
    cup: Optional[str] = None
    data_esecuzione: Optional[str] = None
    profondita_totale_m: Optional[float] = None
    coordinates: Optional[Coordinates] = None
    elevation_m: Optional[float] = None
    falda: Optional[Falda] = None
    pages_source: List[int] = []
    spt: List[SPTMeasure] = []
    permeability: List[PermeabilityMeasure] = []
    parametri: List[dict] = []


class ExtractionResult(BaseModel):
    source_file: str
    detected_profile: Optional[str] = None
    cup: Optional[str] = None
    campaign_year: Optional[str] = None
    sondaggi: List[Sondaggio] = []
    extraction_date: Optional[str] = None
    pipeline_version: str = "v1a-llm"
