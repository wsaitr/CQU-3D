CREATE DATABASE IF NOT EXISTS repo_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE repo_db;

CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    uuid VARCHAR(36) NOT NULL UNIQUE,
    username VARCHAR(64) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_users_username (username),
    INDEX idx_users_email (email)
);

CREATE TABLE IF NOT EXISTS projects (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    uuid VARCHAR(36) NOT NULL UNIQUE,
    user_id BIGINT NOT NULL,
    name VARCHAR(128) NOT NULL,
    description VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_project_user_name (user_id, name),
    INDEX idx_projects_user_id (user_id),
    CONSTRAINT fk_projects_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS assets (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    project_id BIGINT NOT NULL,
    file_type VARCHAR(16) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(1000) NOT NULL,
    file_size INT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_assets_user_id (user_id),
    INDEX idx_assets_project_id (project_id),
    CONSTRAINT fk_assets_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_assets_project_id FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tasks (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NULL,
    project_id BIGINT NULL,
    source_video_path VARCHAR(1000) NOT NULL,
    status VARCHAR(32) NOT NULL,
    progress INT NOT NULL DEFAULT 0,
    mode VARCHAR(16) NOT NULL DEFAULT 'both',
    error_message VARCHAR(2000) NULL,
    output_path VARCHAR(1000) NULL,
    preview_path VARCHAR(1000) NULL,
    log_path VARCHAR(1000) NULL,
    result_meta_path VARCHAR(1000) NULL,
    retry_count INT NOT NULL DEFAULT 0,
    max_retries INT NOT NULL DEFAULT 1,
    worker_id VARCHAR(128) NULL,
    idempotency_key VARCHAR(128) NULL,
    cancel_requested TINYINT(1) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    started_at DATETIME NULL,
    heartbeat_at DATETIME NULL,
    finished_at DATETIME NULL,
    INDEX idx_tasks_status (status),
    INDEX idx_tasks_user_id (user_id),
    INDEX idx_tasks_project_id (project_id),
    INDEX idx_tasks_idempotency_key (idempotency_key)
);
