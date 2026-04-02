"""SQLAlchemy 模型 — 与 sql/01_schema.sql 对齐（member 列与 members.csv 表头一致）。"""
from __future__ import annotations

from datetime import date, datetime
from flask_login import UserMixin
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base, UserMixin):
    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    email: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    genealogies: Mapped[list[Genealogy]] = relationship(
        back_populates="creator", foreign_keys="Genealogy.created_by"
    )


class Genealogy(Base):
    __tablename__ = "genealogy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    surname: Mapped[str] = mapped_column(String(64), nullable=False)
    revision_date: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    creator: Mapped[User] = relationship(
        foreign_keys=[created_by], back_populates="genealogies"
    )
    collaborators: Mapped[list[GenealogyCollaborator]] = relationship(
        back_populates="genealogy", cascade="all, delete-orphan"
    )
    members: Mapped[list[Member]] = relationship(
        back_populates="genealogy",
        foreign_keys="Member.tree_id",
        passive_deletes=True,
    )


class GenealogyCollaborator(Base):
    __tablename__ = "genealogy_collaborator"

    genealogy_id: Mapped[int] = mapped_column(
        ForeignKey("genealogy.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True
    )
    invited_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    joined_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    genealogy: Mapped[Genealogy] = relationship(back_populates="collaborators")


class Member(Base):
    __tablename__ = "member"

    member_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tree_id: Mapped[int] = mapped_column(
        ForeignKey("genealogy.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    gender: Mapped[str] = mapped_column(String(16), nullable=False)
    birth_year: Mapped[int | None] = mapped_column(Integer)
    death_year: Mapped[int | None] = mapped_column(Integer)
    bio: Mapped[str | None] = mapped_column(Text)
    generation_level: Mapped[int | None] = mapped_column(Integer)
    father_id: Mapped[int | None] = mapped_column(ForeignKey("member.member_id"))
    mother_id: Mapped[int | None] = mapped_column(ForeignKey("member.member_id"))
    spouse_id: Mapped[int | None] = mapped_column(ForeignKey("member.member_id"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    genealogy: Mapped[Genealogy] = relationship(
        back_populates="members", foreign_keys=[tree_id]
    )

    __table_args__ = (
        CheckConstraint(
            "death_year IS NULL OR birth_year IS NULL OR death_year >= birth_year",
            name="ck_member_life",
        ),
        CheckConstraint(
            "gender IN ('M','F','Male','Female','男','女')",
            name="ck_member_gender_csv",
        ),
    )
