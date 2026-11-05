-- ============================================================================
-- Mahalla Assistant — qo'lda bajariladigan sxema migratsiyalari
--
-- Repoda Alembic yo'q. `create_all()` mavjud jadvalga yangi ustun qo'shmaydi,
-- shuning uchun sxema o'zgarishlari shu skript orqali bajariladi.
--
-- Qanday bajarish:
--   psql "$DATABASE_URL" -f scripts/migrate.sql
--   yoki Vercel/Neon SQL editor'ida `scripts/migrate.sql` faylini ochib
--   bajarish.
--
-- Har bir blok `IF NOT EXISTS`/DO $$ bilan himoyalangan — skriptni bir necha
-- marta ishga tushirsangiz ham xato bermaydi.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- K-8: Conversation egasini saqlash (IDOR himoyasi)
-- ---------------------------------------------------------------------------
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS user_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_conversations_user_id ON conversations (user_id);

-- ---------------------------------------------------------------------------
-- J-6: Import manba nomi 64 belgidan uzun bo'lishi mumkin
-- ---------------------------------------------------------------------------
ALTER TABLE citizens
    ALTER COLUMN data_source TYPE VARCHAR(255);

-- ---------------------------------------------------------------------------
-- N-10: Kredit bank tanlovi kaliti takrorlanmasligi uchun
-- ---------------------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS uq_memory_item_key_conversation
    ON memory_items (key, conversation_id);
