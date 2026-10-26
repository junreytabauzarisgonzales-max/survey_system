-- Hosted PostgreSQL schema, equivalent to SQLite migrations 001 through 003.
-- JSON documents remain TEXT so service snapshots retain their original encoding.
CREATE TABLE users(id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, name TEXT NOT NULL, password TEXT NOT NULL, admin INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE sessions(token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires TEXT NOT NULL);
CREATE TABLE projects(id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL, config TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE memberships(project_id TEXT NOT NULL REFERENCES projects(id), user_id TEXT NOT NULL REFERENCES users(id), role TEXT NOT NULL CHECK(role IN ('manager','researcher','viewer')), identifiable INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(project_id,user_id));
CREATE TABLE forms(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), name TEXT NOT NULL, draft TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, archived INTEGER NOT NULL DEFAULT 0);
CREATE TABLE versions(id TEXT PRIMARY KEY, form_id TEXT NOT NULL REFERENCES forms(id), number INTEGER NOT NULL, schema TEXT NOT NULL, published_at TEXT NOT NULL, published_by TEXT NOT NULL REFERENCES users(id), UNIQUE(form_id,number));
CREATE TABLE respondents(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), researcher_id TEXT NOT NULL REFERENCES users(id), data TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE public_links(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), version_id TEXT NOT NULL REFERENCES versions(id), token TEXT NOT NULL UNIQUE, name TEXT NOT NULL, created_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, expires_at TEXT, enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)), revision INTEGER NOT NULL DEFAULT 1, locations TEXT NOT NULL);
CREATE TABLE interviews(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), version_id TEXT NOT NULL REFERENCES versions(id), researcher_id TEXT REFERENCES users(id), respondent_id TEXT REFERENCES respondents(id), location TEXT, status TEXT NOT NULL CHECK(status IN ('draft','completed')), answers TEXT NOT NULL, consent INTEGER NOT NULL, location_consent INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, source TEXT NOT NULL DEFAULT 'researcher' CHECK(source IN ('researcher','public_link')), public_link_id TEXT REFERENCES public_links(id), CHECK((source='researcher' AND researcher_id IS NOT NULL AND public_link_id IS NULL) OR (source='public_link' AND researcher_id IS NULL AND public_link_id IS NOT NULL)));
CREATE TABLE corrections(id TEXT PRIMARY KEY, interview_id TEXT NOT NULL REFERENCES interviews(id), answers TEXT NOT NULL, reason TEXT NOT NULL, actor_id TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, _sequence BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE);
CREATE TABLE sync_events(id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), fingerprint TEXT NOT NULL, result TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE history(id TEXT PRIMARY KEY, resource_type TEXT NOT NULL, resource_id TEXT NOT NULL, actor_id TEXT NOT NULL REFERENCES users(id), snapshot TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE export_audits(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), actor_id TEXT NOT NULL REFERENCES users(id), options TEXT NOT NULL, record_count INTEGER NOT NULL, created_at TEXT NOT NULL, state TEXT NOT NULL);
CREATE TABLE retention_events(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), actor_id TEXT NOT NULL REFERENCES users(id), record_count INTEGER NOT NULL, cutoff TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE attachments(id TEXT PRIMARY KEY, interview_id TEXT NOT NULL REFERENCES interviews(id), question_id TEXT NOT NULL, filename TEXT NOT NULL, mime TEXT NOT NULL, content BYTEA NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE public_receipts(submission_id TEXT PRIMARY KEY, link_id TEXT NOT NULL REFERENCES public_links(id), fingerprint TEXT NOT NULL, interview_id TEXT UNIQUE REFERENCES interviews(id) ON DELETE SET NULL, receipt TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
CREATE TABLE project_deletions(project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE);
CREATE TABLE request_limits(bucket TEXT PRIMARY KEY, started_at BIGINT NOT NULL, hits INTEGER NOT NULL);
CREATE INDEX request_limits_expiry ON request_limits(started_at);
CREATE INDEX interviews_project ON interviews(project_id,version_id,created_at);
CREATE INDEX interviews_public_link ON interviews(public_link_id);
CREATE INDEX corrections_interview ON corrections(interview_id,_sequence);
CREATE INDEX history_resource ON history(resource_type,resource_id,created_at);

CREATE FUNCTION survey_immutable_record() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Immutable record in %', TG_TABLE_NAME USING ERRCODE='23514';
END;
$$;
CREATE FUNCTION survey_protect_completed() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status='completed' THEN
    RAISE EXCEPTION 'Use a tracked correction' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END;
$$;
CREATE FUNCTION survey_protect_version_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM project_deletions d JOIN forms f ON f.project_id=d.project_id WHERE f.id=OLD.form_id) THEN
    RAISE EXCEPTION 'Published versions are immutable' USING ERRCODE='23514';
  END IF;
  RETURN OLD;
END;
$$;
CREATE TRIGGER immutable_versions_update BEFORE UPDATE ON versions FOR EACH ROW EXECUTE FUNCTION survey_immutable_record();
CREATE TRIGGER immutable_versions_delete BEFORE DELETE ON versions FOR EACH ROW EXECUTE FUNCTION survey_protect_version_delete();
CREATE TRIGGER immutable_completed BEFORE UPDATE ON interviews FOR EACH ROW EXECUTE FUNCTION survey_protect_completed();
CREATE TRIGGER immutable_corrections BEFORE UPDATE ON corrections FOR EACH ROW EXECUTE FUNCTION survey_immutable_record();
CREATE TRIGGER immutable_public_link_version BEFORE UPDATE OF project_id,version_id,token ON public_links FOR EACH ROW EXECUTE FUNCTION survey_immutable_record();
