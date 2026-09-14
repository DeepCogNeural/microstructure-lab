# Data Terms

## Coinbase restriction (checked September 14, 2026 UTC)

The [official Market Data Terms](https://www.coinbase.com/legal/market_data)
are dated August 7, 2026. Section 3.5 requires prior express written consent
for using market data to develop, train, validate, benchmark or improve AI/ML
models or algorithms. Section 3.2 also restricts external dissemination of
derived charts, analytics and research. Public access does not authorize the
ML workflow. Keep the Coinbase adapter as engineering infrastructure; do not
collect or reuse Coinbase captures for this benchmark without permission.
Earlier Coinbase smoke outputs are not accepted empirical evidence.

The selected empirical benchmark is WSELOB-2017, explicitly published under
CC BY 4.0 by its depositor; see [evidence and attribution](WSELOB_LICENSE.md).
Its derived aggregates may be published with attribution, a license link,
modifications notice and the applicable as-is/no-warranty notice. Raw files
remain ignored. FI-2010 was also license-checked, but was not used; see
[candidate evidence](FI2010_LICENSE.md).

This project does not commit raw market data. The only real-data reports
published here are aggregates from an explicitly permitted dataset, under
that dataset's applicable license and attribution requirements.

## Repository Policy

- Commit code, schemas, documentation, tests, and small deterministic fixtures.
- Do not commit private keys, API keys, wallets, credentials, or account data.
- Do not commit paid, licensed, or proprietary datasets.
- Do not commit large raw publicly accessible feed captures.
- Treat publicly accessible feeds as subject to provider terms.
- MIT covers this software only; it grants no rights to third-party market
  data.

## Operator Responsibility

If you run a public collector, you are responsible for checking the relevant
venue terms before storing, sharing, or publishing captured data. The offline
demo is synthetic and does not depend on venue data.
