# TRACE-Net Route Confidence Resolver v1 Front-Matter Clamp

This focused patch tightens `trace_net_route_confidence_resolver_v1` so repeated manual header/footer identity text does not cause content pages to be routed as `cover_or_title_page`.

## Fix

The previous resolver could treat weak page identity fragments such as `T.P. 120/1176`, revision dates, or manufacturer footer text as cover/title evidence. On the full 509-page run, this produced an implausibly high `cover_or_title_page` count.

This patch separates strong cover/title identity signals from weak header/footer signals:

- strong: `component maintenance manual`, `passenger seats`, `this publication supersedes`, `publication covers`
- weak: `revision`, `embraer`, `t.p.`

A page can now become `cover_or_title_page` only when strong title identity is present with appropriate front-matter layout/page-position constraints. Weak header/footer text alone is ignored as a cover/title trigger.

## Safety contract

No Postgres writes, no Qdrant writes, no OpenSearch writes, no source-truth mutation, no answer permission.
