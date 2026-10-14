-- pgcrypto provides gen_random_uuid() for the UUID primary keys in §6.1.
-- Runs once, on first initialization of an empty data volume.
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
