-- A project deletion marker lets the service purge a survey's published
-- versions in the same transaction while direct version deletes stay blocked.
CREATE TABLE project_deletions(
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE
);
DROP TRIGGER immutable_versions_delete;
CREATE TRIGGER immutable_versions_delete BEFORE DELETE ON versions
WHEN NOT EXISTS (
    SELECT 1 FROM project_deletions d
    JOIN forms f ON f.project_id=d.project_id
    WHERE f.id=OLD.form_id
)
BEGIN SELECT RAISE(ABORT,'Published versions are immutable'); END;
