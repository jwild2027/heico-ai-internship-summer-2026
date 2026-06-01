# Page image-recognition quality final parser fix

This patch replaces the image-recognition quality checker with a robust parser that accepts the current audit JSON field names and older field variants.

It fixes false failures where the audit clearly reports `Readable images: 509` but the quality checker read `0`.
