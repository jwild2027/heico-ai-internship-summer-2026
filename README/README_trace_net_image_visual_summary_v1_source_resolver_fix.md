# TRACE-Net Image Visual Summary v1 Source Resolver Fix

Fixes image source resolution for ResCarta-style `metadata.zip` packages that store page rasters as bare eight-digit TIFF names such as `00000001.tif`.

The image visual summary module already found the 12 `image_visual` routed pages, but it reported all image sources as missing because the resolver did not treat bare eight-digit TIFF stems as page numbers.

This patch:

- expands page-number parsing to support 1-8 digit tokens in image filenames;
- explicitly handles bare numeric image stems such as `00000001.tif`;
- preserves tagged ID support such as `source_p000001`, `metadata_page_000001`, `p000001`, and `zip_page_000001_00000001.tif`;
- adds `image_source_candidates` to each visual summary card for inspectability;
- adds a regression test proving pages `p000001` and `p000012` resolve to `00000001.tif` and `00000012.tif` inside a metadata ZIP.

Safety remains unchanged: no answer permission, no source-truth mutation, and no database/vector/search writes.
