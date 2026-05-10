"""数据库连接和轻量迁移。"""

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from packages.shared.config import settings
from packages.shared.models import Base

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

TASK_MIGRATIONS: dict[str, str] = {
    "user_id": "ALTER TABLE tasks ADD COLUMN user_id BIGINT NULL",
    "project_id": "ALTER TABLE tasks ADD COLUMN project_id BIGINT NULL",
    "source_video_path": "ALTER TABLE tasks ADD COLUMN source_video_path VARCHAR(1000) NOT NULL DEFAULT ''",
    "mode": "ALTER TABLE tasks ADD COLUMN mode VARCHAR(16) NOT NULL DEFAULT 'both'",
    "error_message": "ALTER TABLE tasks ADD COLUMN error_message VARCHAR(2000) NULL",
    "output_path": "ALTER TABLE tasks ADD COLUMN output_path VARCHAR(1000) NULL",
    "preview_path": "ALTER TABLE tasks ADD COLUMN preview_path VARCHAR(1000) NULL",
    "log_path": "ALTER TABLE tasks ADD COLUMN log_path VARCHAR(1000) NULL",
    "result_meta_path": "ALTER TABLE tasks ADD COLUMN result_meta_path VARCHAR(1000) NULL",
    "retry_count": "ALTER TABLE tasks ADD COLUMN retry_count INT NOT NULL DEFAULT 0",
    "max_retries": "ALTER TABLE tasks ADD COLUMN max_retries INT NOT NULL DEFAULT 1",
    "worker_id": "ALTER TABLE tasks ADD COLUMN worker_id VARCHAR(128) NULL",
    "idempotency_key": "ALTER TABLE tasks ADD COLUMN idempotency_key VARCHAR(128) NULL",
    "cancel_requested": "ALTER TABLE tasks ADD COLUMN cancel_requested TINYINT(1) NOT NULL DEFAULT 0",
    "started_at": "ALTER TABLE tasks ADD COLUMN started_at DATETIME NULL",
    "heartbeat_at": "ALTER TABLE tasks ADD COLUMN heartbeat_at DATETIME NULL",
    "finished_at": "ALTER TABLE tasks ADD COLUMN finished_at DATETIME NULL",
}


async def get_session():
    async with AsyncSessionLocal() as session:
        yield session


def _table_exists(sync_conn, table_name: str) -> bool:
    inspector = inspect(sync_conn)
    return table_name in inspector.get_table_names()


def _missing_column_sql(sync_conn, table_name: str, migrations: dict[str, str]) -> list[str]:
    inspector = inspect(sync_conn)
    existing = {item["name"] for item in inspector.get_columns(table_name)}
    return [sql for name, sql in migrations.items() if name not in existing]


def _index_exists(sync_conn, table_name: str, index_name: str) -> bool:
    inspector = inspect(sync_conn)
    indexes = inspector.get_indexes(table_name)
    return any(item.get("name") == index_name for item in indexes)


async def init_models() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        exists = await conn.run_sync(_table_exists, "tasks")
        if not exists:
            return

        statements = await conn.run_sync(_missing_column_sql, "tasks", TASK_MIGRATIONS)
        for statement in statements:
            await conn.execute(text(statement))

        has_idempotency_index = await conn.run_sync(_index_exists, "tasks", "idx_tasks_idempotency_key")
        if not has_idempotency_index:
            await conn.execute(text("CREATE INDEX idx_tasks_idempotency_key ON tasks (idempotency_key)"))

        has_project_index = await conn.run_sync(_index_exists, "tasks", "idx_tasks_project_id")
        if not has_project_index:
            await conn.execute(text("CREATE INDEX idx_tasks_project_id ON tasks (project_id)"))
