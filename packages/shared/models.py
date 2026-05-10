"""共享数据库模型。"""

import uuid

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[str] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_project_user_name"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[str] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True, nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("projects.id"), index=True, nullable=False)
    file_type: Mapped[str] = mapped_column(String(16), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    project_id: Mapped[int | None] = mapped_column(BigInteger, index=True)

    source_video_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", index=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="both")

    error_message: Mapped[str | None] = mapped_column(String(2000))
    output_path: Mapped[str | None] = mapped_column(String(1000))
    preview_path: Mapped[str | None] = mapped_column(String(1000))
    log_path: Mapped[str | None] = mapped_column(String(1000))
    result_meta_path: Mapped[str | None] = mapped_column(String(1000))

    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    worker_id: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str | None] = mapped_column(String(128), index=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[str] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[str] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    started_at: Mapped[str | None] = mapped_column(DateTime)
    heartbeat_at: Mapped[str | None] = mapped_column(DateTime)
    finished_at: Mapped[str | None] = mapped_column(DateTime)
