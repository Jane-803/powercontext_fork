CREATE DATABASE IF NOT EXISTS traceboard DEFAULT CHARACTER SET utf8mb4;
USE traceboard;

CREATE TABLE IF NOT EXISTS evidence (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  project VARCHAR(100) NOT NULL,
  kind VARCHAR(20) NOT NULL,
  title VARCHAR(200) NOT NULL,
  content TEXT NOT NULL,
  source_url VARCHAR(500) NOT NULL DEFAULT '',
  occurred_on DATE NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_project_date (project, occurred_on),
  FULLTEXT KEY idx_evidence_text (title, content) WITH PARSER ik
);

CREATE TABLE IF NOT EXISTS tasks (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  project VARCHAR(100) NOT NULL,
  title VARCHAR(200) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'todo',
  due_on DATE NULL,
  evidence_id BIGINT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_task_project (project, status)
);
