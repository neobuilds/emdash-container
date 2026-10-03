# EmDash Blog container

Independent deployment packaging for [EmDash](https://github.com/emdash-cms/emdash), not an upstream-official image or application fork.

## Contents and provenance

- EmDash 1.1.0 and the unchanged upstream Blog theme from commit `913cb1bb9b7f08c3ff0d258b4420e53835b6a58e`, downloaded with a pinned SHA-256 checksum.
- Astro standalone Node server, SQLite, local uploads, and the enabled `@emdash-cms/sandbox-workerd` 0.9.2 runner with workerd 1.20261002.1.
- Node 22.23.3 Debian Bookworm slim base pinned by multi-architecture digest; npm dependencies locked to public npm registry artifacts.
- Configuration-only overlays put the SQLite database and Astro sessions under `/app/data` and enable the workerd runner. No theme/application source changes.
- The upstream MIT license is copied to `/app/LICENSE.upstream`. Dependencies retain their own license notices.

Only explicit packaging inputs enter the image. Repository README, workflows, tests and Git history are not copied into it. Image metadata links to this EmDash-specific repository, not a private template repository.

## Release workflow

The manually dispatched workflow follows native amd64/arm64 build → boot/workerd/recreation test → all-layer and metadata audit → digest publication. Only after both native jobs pass does it publish `ghcr.io/neobuilds/emdash:1.1.0-<packaging-commit>`.

It authenticates with this repository's GitHub Actions token (`packages: write`), not a copied personal credential. A new package may initially be private: package visibility and anonymous pulls are separate release gates. Never assume a successful push means public availability. Consumers should pin the version-bearing tag and multi-architecture index digest.

`audit-image.py` scans every saved layer, including files hidden by later layers, for private repository references, credential signatures and sensitive file paths; it inventories non-dependency README hashes. This is a heuristic review, not a guarantee that arbitrary secrets cannot exist. Build-input allowlisting is also required.

## Runtime

Serve container port 4321 behind an HTTPS reverse proxy. Set `EMDASH_SITE_URL` to the public HTTPS origin and supply `EMDASH_ENCRYPTION_KEY_HEX` as 64 lowercase hexadecimal characters generated securely for that installation. The startup wrapper derives the upstream key in memory without logging it.

Persist `/app/data` and `/app/uploads`. Back up both together and preserve the encryption key separately. Claim `/_emdash/admin` immediately and register the first owner's passkey over HTTPS. There is no default password. Email/OAuth/object-storage integrations are not preconfigured.

Plugins remain sandboxed in workerd; upstream Node-hosted sandbox limits are weaker than Cloudflare Workers. This is not a hostile multi-tenant execution service. No Docker socket or privileged container is needed.

Native boot and volume-marker tests are not full CMS onboarding or managed-platform certification. Upgrades require coordinated backups and review of upstream migrations; changing a catalog/image reference does not upgrade existing installations automatically.
