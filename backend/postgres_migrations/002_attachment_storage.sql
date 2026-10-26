-- Hosted attachments may live in Neon Object Storage. Channel-compatible
-- clients use 7-column inserts; hosted service code stores the bucket key and
-- leaves the inline BYTEA empty.
ALTER TABLE attachments ADD COLUMN storage_key TEXT;
