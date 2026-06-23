# Limitations

This repo is a public research scaffold. Its limits are deliberate and should
be stated plainly.

## Data Limits

- The committed demo data is synthetic.
- Publicly accessible forward collection starts only when the collector runs.
- The repo does not redistribute captured venue data or derived real-data
  reports.
- Exchange feeds can have reconnects, gaps, dropped messages, and same
  timestamp events.
- Coinbase `match.side` is documented as maker side. Aggressor-side features
  must invert that field before using trade direction.

## Market-Microstructure Limits

- Aggregate L2 does not reveal hidden liquidity.
- Aggregate L2 does not prove queue position or passive fill probability.
- Visible-depth sweep cost is a crossing-cost proxy, not an execution simulator.
- Midpoint markout is not PnL.
- A positive in-sample metric is not evidence of a tradable strategy.

## Modeling Limits

- The default model is intentionally linear.
- Overlapping markout horizons create dependent labels.
- Results can change with symbol, venue, clock quality, market regime, and fee
  assumptions.
- More complex models need stronger out-of-sample tests and additional
  negative controls.
