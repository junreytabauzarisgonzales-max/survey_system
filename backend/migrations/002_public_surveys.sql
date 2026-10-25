-- rebuild-with-foreign-keys-off
-- SQLite cannot remove NOT NULL from researcher_id in place. Copy all original
-- rows unchanged, preserve child foreign-key targets, then restore the trigger.
CREATE TABLE public_links(
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    version_id TEXT NOT NULL REFERENCES versions(id),
    token TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    expires_at TEXT,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
    revision INTEGER NOT NULL DEFAULT 1,
    locations TEXT NOT NULL
);
CREATE TABLE interviews_new(
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    version_id TEXT NOT NULL REFERENCES versions(id),
    researcher_id TEXT REFERENCES users(id),
    respondent_id TEXT REFERENCES respondents(id),
    location TEXT,
    status TEXT NOT NULL CHECK(status IN ('draft','completed')),
    answers TEXT NOT NULL,
    consent INTEGER NOT NULL,
    location_consent INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT 'researcher' CHECK(source IN ('researcher','public_link')),
    public_link_id TEXT REFERENCES public_links(id),
    CHECK((source='researcher' AND researcher_id IS NOT NULL AND public_link_id IS NULL)
       OR (source='public_link' AND researcher_id IS NULL AND public_link_id IS NOT NULL))
);
INSERT INTO interviews_new(id,project_id,version_id,researcher_id,respondent_id,location,status,answers,consent,location_consent,created_at,updated_at,revision)
    SELECT id,project_id,version_id,researcher_id,respondent_id,location,status,answers,consent,location_consent,created_at,updated_at,revision FROM interviews;
DROP TABLE interviews;
ALTER TABLE interviews_new RENAME TO interviews;
CREATE INDEX interviews_project ON interviews(project_id,version_id,created_at);
CREATE INDEX interviews_public_link ON interviews(public_link_id);
CREATE TRIGGER immutable_completed BEFORE UPDATE ON interviews WHEN OLD.status='completed' BEGIN SELECT RAISE(ABORT,'Use a tracked correction'); END;
CREATE TRIGGER immutable_public_link_version BEFORE UPDATE OF project_id,version_id,token ON public_links BEGIN SELECT RAISE(ABORT,'Public link version and token are immutable'); END;
CREATE TABLE public_receipts(
    submission_id TEXT PRIMARY KEY,
    link_id TEXT NOT NULL REFERENCES public_links(id),
    fingerprint TEXT NOT NULL,
    interview_id TEXT UNIQUE REFERENCES interviews(id) ON DELETE SET NULL,
    receipt TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
