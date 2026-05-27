# Incremental preview DB cleanup fix

This patch fixes Windows dry-run/preview behavior for the incremental TIFF state DB.

Python's `sqlite3.Connection` context manager does not close the file handle; it
only commits or rolls back the transaction. Preview tests expect no DB file to be
left behind when no state is committed. This patch explicitly closes SQLite
connections and removes any empty SQLite sidecar files created during preview.

It keeps safe-commit behavior intact: state is committed only after downstream
processing succeeds.
