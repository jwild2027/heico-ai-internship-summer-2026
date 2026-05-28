# Document organization audit pipeline compatibility fix

This patch fixes the pipeline failure:

```text
audit_document_organization.py: error: unrecognized arguments: --no-refresh-manifest
```

The normal backend pipeline already passes `--no-refresh-manifest` to audit-style commands so the pipeline runner controls manifest writing. The document organization audit command did not accept that argument yet.

This patch adds `--no-refresh-manifest` as a no-op compatibility flag to:

```text
scripts/audit_document_organization.py
```

No database behavior changes. No organization logic changes. The command simply accepts the pipeline flag and continues.
