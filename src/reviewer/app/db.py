"""Persistence for contracts, reviews, findings, and human decisions.

SQLite by default so the pilot runs with zero infrastructure. Set DATABASE_URL to a
Postgres URL for the firm's deployment; the schema is plain SQLAlchemy and needs no
SQLite-specific features. Every human decision is a row with a name and a timestamp:
that audit trail is the product as much as the findings are.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Contract(Base):
    __tablename__ = "contracts"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(100))
    text: Mapped[str] = mapped_column(Text)
    page_starts: Mapped[str] = mapped_column(Text, default="[0]")  # JSON list
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    reviews: Mapped[list[Review]] = relationship(back_populates="contract", cascade="all, delete")


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"))
    reviewer_name: Mapped[str] = mapped_column(String(50))  # which system produced it
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    contract: Mapped[Contract] = relationship(back_populates="reviews")
    findings: Mapped[list[Finding]] = relationship(back_populates="review", cascade="all, delete")


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id"))
    clause_type: Mapped[str] = mapped_column(String(50))
    present: Mapped[int] = mapped_column(Integer)  # bool as int for SQLite portability
    rationale: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(
        String(20), default="proposed"
    )  # proposed|approved|rejected
    decided_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    review: Mapped[Review] = relationship(back_populates="findings")
    citations: Mapped[list[Citation]] = relationship(
        back_populates="finding", cascade="all, delete"
    )


class Citation(Base):
    __tablename__ = "citations"
    id: Mapped[int] = mapped_column(primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id"))
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    page: Mapped[int] = mapped_column(Integer, default=1)
    text: Mapped[str] = mapped_column(Text)
    finding: Mapped[Finding] = relationship(back_populates="citations")


def make_engine(url: str | None = None):
    url = url or os.environ.get("DATABASE_URL", "sqlite:///./data/reviewer.db")
    if url.startswith("sqlite:///./"):
        os.makedirs(os.path.dirname(url.removeprefix("sqlite:///")), exist_ok=True)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args)
    Base.metadata.create_all(engine)
    return engine


def make_session_factory(url: str | None = None):
    return sessionmaker(bind=make_engine(url), expire_on_commit=False)
