ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS user_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_conversations_user_id ON conversations (user_id);

ALTER TABLE citizens
    ALTER COLUMN data_source TYPE VARCHAR(255);

CREATE UNIQUE INDEX IF NOT EXISTS uq_memory_item_key_conversation
    ON memory_items (key, conversation_id);

ALTER TABLE backup_runs
    ADD COLUMN IF NOT EXISTS data BYTEA;

UPDATE users
SET permissions = COALESCE(permissions, '[]'::jsonb) || '["reports.approve"]'::jsonb
WHERE role = 'admin'
  AND NOT (COALESCE(permissions, '[]'::jsonb) ? 'reports.approve');
