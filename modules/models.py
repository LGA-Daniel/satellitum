from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, DateTime, Float, UniqueConstraint, func
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
