from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, DateTime, Float, UniqueConstraint, ForeignKey, Text, func
from datetime import datetime
from typing import Optional

class Base(DeclarativeBase):
    pass

class HistoricoExecucao(Base):
    __tablename__ = "historico_execucoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome_arquivo: Mapped[str] = mapped_column(String(255), nullable=False)
    script: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    data_execucao: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def to_dict(self) -> dict:
        """Retorna os dados do modelo como dicionário."""
        return {
            "id": self.id,
            "nome_arquivo": self.nome_arquivo,
            "script": self.script,
            "status": self.status,
            "data_execucao": self.data_execucao.isoformat() if self.data_execucao else None
        }

class MetadadosImagens(Base):
    __tablename__ = "metadados_imagens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data: Mapped[str] = mapped_column(String(50), nullable=False)
    pixels_validos: Mapped[int] = mapped_column(Integer, nullable=False)
    satelite: Mapped[str] = mapped_column(String(100), nullable=False)
    zenital: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    z_grade_mgrs: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tamanho_pixel: Mapped[int] = mapped_column(Integer, nullable=False)
    data_registro: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('data', 'satelite', 'z_grade_mgrs', 'tamanho_pixel', name='uq_metadados_imagem'),
    )

    def to_dict(self) -> dict:
        """Retorna os dados do modelo como dicionário."""
        return {
            "id": self.id,
            "data": self.data,
            "pixels_validos": self.pixels_validos,
            "satelite": self.satelite,
            "zenital": self.zenital,
            "z_grade_mgrs": self.z_grade_mgrs,
            "tamanho_pixel": self.tamanho_pixel,
            "data_registro": self.data_registro.isoformat() if self.data_registro else None
        }

class CelmmPixels(Base):
    __tablename__ = "celmm_pixels"

    __table_args__ = (
        UniqueConstraint('metadados_imagem_id', 'system_index', name='uq_celmm_pixel'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metadados_imagem_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("metadados_imagens.id", ondelete="CASCADE"), 
        nullable=False
    )
    system_index: Mapped[str] = mapped_column(String(100), nullable=False)
    data: Mapped[str] = mapped_column(String(50), nullable=False)
    satelite: Mapped[str] = mapped_column(String(100), nullable=False)
    z_grade_mgrs: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tamanho_pixel: Mapped[int] = mapped_column(Integer, nullable=False)
    zenital: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Bandas espectrais
    B1: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    B2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    B3: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    B4: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    B5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    B6: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    B7: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    B8: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    B8A: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    B9: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    B11: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    B12: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Coordenadas geográficas
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Geometria geojson
    geo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    data_registro: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def to_dict(self) -> dict:
        """Retorna os dados do modelo como dicionário."""
        return {
            "id": self.id,
            "metadados_imagem_id": self.metadados_imagem_id,
            "system_index": self.system_index,
            "data": self.data,
            "satelite": self.satelite,
            "z_grade_mgrs": self.z_grade_mgrs,
            "tamanho_pixel": self.tamanho_pixel,
            "zenital": self.zenital,
            "B1": self.B1,
            "B2": self.B2,
            "B3": self.B3,
            "B4": self.B4,
            "B5": self.B5,
            "B6": self.B6,
            "B7": self.B7,
            "B8": self.B8,
            "B8A": self.B8A,
            "B9": self.B9,
            "B11": self.B11,
            "B12": self.B12,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "geo": self.geo,
            "data_registro": self.data_registro.isoformat() if self.data_registro else None
        }
