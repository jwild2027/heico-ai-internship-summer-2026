# Document organization export summary fix

Fixes a bookkeeping mismatch where the export command wrote five organization JSON files, but `organization_summary.json` listed only four. The quality gate reads `organization_summary.json`, so it incorrectly failed `document_organization_export_files`.

The fix makes `organization_summary.json` include itself in `files_written`, matching the command output and returned summary.
