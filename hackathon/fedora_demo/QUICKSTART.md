# Fedora judge demo quickstart

## What this starts

Nothing. This guide uses the already running, localhost-only AgrregateX demo at
`http://127.0.0.1:8093/`. It does not start, stop, rebuild, seed, migrate, or
write to a database. The verified setup has one PostgreSQL database and one
configured shard named `default`.

## Before judges arrive

1. Open `http://127.0.0.1:8093/` and confirm the AgrregateX landing page loads.
2. Select **OPEN DASHBOARD**. Confirm the URL becomes
   `http://127.0.0.1:8093/app#/dashboard`.
3. Confirm the tenant selector and the four analytics panels load.
4. Use the sidebar to visit **Shards**, **pg_trickle Engine**, and **Live
   Monitoring**. Shards must show one `DEFAULT` shard, not A/B.
5. If the page is unavailable, stop: do not restart services or touch volumes
   during the presentation. Use the committed screenshots and the recorded
   read-only evidence instead.

Optional bounded API check (one request per endpoint, GET only):

```sh
python3 hackathon/fedora_demo/smoke.py
```

The smoke tool only accepts loopback URLs and has a 4-second request timeout.
It does not log in, create a session, mutate orders, rebuild summaries, or
print credentials. The local service currently uses the explicit operator
bypass (`AX_AUTH_DISABLED=1`) with demo writes disabled. This mode is for this
localhost demo only; it does not prove secure-mode authentication or tenant
isolation. Normal deployments default to authentication enabled.

## Safe operating rules

- Never run `docker compose down -v`, reset a database, delete a volume, or
  execute initialization SQL against this working database.
- Do not press any live-mutation controls. Writes are disabled on this demo.
- Do not represent Fedora's one-shard view as the separate Mac two-shard
  failure-recovery demo.
- The counts in screenshots are point-in-time representative demo data, not
  organizer data or an official-scale benchmark.
- Preserve upstream `pg_trickle` attribution and Apache-2.0 licensing.

## Recovery / fallback

If a live page fails, switch to the screenshots under
`hackathon/docs/fedora-evidence/screenshots/`. For current API and source-count
evidence, use `hackathon/docs/fedora-evidence/RESULTS.md`. Say explicitly that
the fallback is captured evidence, not a live service.
