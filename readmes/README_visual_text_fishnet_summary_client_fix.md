# Visual text fishnet summary client fix

Fixes a crash at the end of a successful fishnet run:

```text
AttributeError: 'NoneType' object has no attribute 'provider_name'
```

The page processing had succeeded, but the final summary tried to read
`client.provider_name`. In normal CLI runs the optional `client` argument is
`None`; the runner builds an internal `base_client` instead. The fix writes the
final summary from `base_client`.

This does not rerun pages and does not change visual extraction behavior. It only
allows the final summary/artifacts to complete after a fishnet run.

After applying, rerun the same fishnet command. With `--overwrite`, it will start
a new run. If you want to preserve current records and only finish/retry errors,
use `--retry-errors-only` when there are actual error records.
