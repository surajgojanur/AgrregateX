# CI PostgreSQL Setup Failure Analysis

## Observed failure

GitHub Actions run [41256340026](https://github.com/surajgojanur/AgrregateX/actions/runs/41256340026) failed in both the Linux unit-test job (`124700615498`) and integration-test job (`124700615639`) at the shared `Setup pgrx environment` step. The relevant log reports:

```text
curl: (56) Failure when receiving data from the peer
Process completed with exit code 56
```

The failing command was the HTTPS download of the PGDG signing key from `https://www.postgresql.org/media/keys/ACCC4CF8.asc` in `.github/actions/setup-pgrx/action.yml`. The preceding `apt-get update` and installation of curl/CA certificates/GnuPG completed. Both jobs stopped during provisioning, so neither Rust unit tests nor integration tests ran. This is not evidence of a test assertion failure.

The evidence establishes a peer-closed transfer reported by curl 56. It does not identify which network hop closed the connection. There is no evidence in this run of TLS verification being disabled, GPG verification failing, runner resource exhaustion, or package-version incompatibility.

## Narrow correction

The shared action now retries only the idempotent signing-key download up to three times after the initial attempt, with bounded connect/overall timeouts. It restricts both the initial request and redirects to HTTPS, requires TLS 1.2 or later, leaves certificate verification enabled, verifies a nonempty temporary download, and installs the key with predictable permissions before the existing APT `signed-by` configuration. APT package signature checks remain unchanged. The retry does not suppress failures.

## Local validation

This change was reviewed statically. YAML parsing and extraction of the Bash run block are checked with the commands in the PR validation record. No GitHub-hosted runner was launched by this investigation. Passing static checks does not prove the next hosted run will succeed.

## Next experiment

Observe the next ordinary workflow run using this action, or request a separately approved low-cost CI rerun. Confirm that the key fetch succeeds, APT retains signature verification, and both jobs proceed into their test steps. If it fails again, capture curl's retry attempts and the subsequent HTTP/TLS status before changing the network setup.
