# WSELOB queue semantics and identification limits

Status: source audit completed; conditional diagnostics are published in [the execution report](QUEUE_AWARE_EXECUTION_REPORT.md).

## Public evidence

The source is [Marszałek (2023), WSELOB-2017 V1](https://data.mendeley.com/datasets/3g4mhdp899/1), DOI 10.17632/3g4mhdp899.1, CC BY 4.0. This study adds replay and execution diagnostics; no endorsement or warranty is implied.

The depositor's [order_data.ipynb](https://data.mendeley.com/public-files/datasets/3g4mhdp899/files/c035b1b9-e70e-4cf5-afcc-92cadd97543e/file_downloaded) documents the fields. The accompanying [orderbook2.py](https://data.mendeley.com/public-files/datasets/3g4mhdp899/files/5d47c404-7a05-4423-8867-c42863a1de57/file_downloaded) implements order updates and sorts orders by price and priority timestamp. Public file metadata lists SHA256 `ed17b84f48d4bcd781172859b36011f3195af23eb73dfd99c067e184342eac79` and `a34bba48ab4a96a80544f10e02c02755c5add38b675a48929550d43aa6eea5de`, respectively.

## Action interpretation

| Action | Documented operation | Permitted inference |
| --- | --- | --- |
| A | Add a new order | Visible order enters the book; duplicate live identity is invalid. |
| Y | Retransmit an order | State recovery, **not a trade**. The supplied code updates an existing identity or adds a missing identity. |
| M | Modify an existing order; the notebook mentions partial fills | A reduction in displayed quantity is consistent with partial execution. The source does not establish that every reduction is exclusively a trade. |
| D | Delete the identified order | The order leaves visible depth. The provided fields do not establish cancellation versus full execution. |
| F | Clear the instrument before start-of-day retransmission | Reset all live state and cancel every virtual order. |

Order identity is instrument plus order date plus order ID. Price is the integer price divided by ten to the power of `price_level`. Displayed `volume` is quantity, not signed traded volume. Use one dataset-native quantity unit; the notebook alone does not independently establish exchange lot conversion, so do not describe this as one exchange lot.

## Priority and modifications

`priority_date` records an order's priority timestamp; `-1` means omitted. The reference code retains omitted fields, including priority. It sorts by price and priority timestamp, but does not document tie-breaking among equal timestamps, hidden quantity, or the exchange's complete amendment rules.

For a supplied priority timestamp, retain the recorded value. For an omitted timestamp, retain the previous timestamp as the reference reconstruction does. A price change places the order in a different price queue. Same-price quantity decrease, increase, and unchanged quantity must be represented separately in diagnostics: retaining priority is a documented replay behavior, **not proof of the venue's matching rule**. An alternative diagnostic moves an ambiguously modified order to the back. These interpretations are assumptions, not an identified exchange rule. A record index can break timestamp ties deterministically, but is only a proxy for actual matching priority.

## Session boundaries

Keep the existing 10:00 inclusive to 16:00 exclusive Warsaw-time window. An F reset, unpriced order, locked/crossed book, insufficient ten-level depth, or a gap in valid original-message indices ends a valid segment. Virtual orders and post-fill outcomes cannot cross those boundaries. The order schema does not independently identify every auction or trading-phase transition. Being inside this clock window and having a valid visible book does not prove continuous matching eligibility.

## Consequence for the experiment

Exact passive fills are not identified by these order messages alone. Neither declining aggregate depth nor a Y message is execution evidence. In particular, cancellation of all orders ahead establishes an empty queue ahead, not consumption of the virtual order itself.

The unconditional identified lower fill bound is zero when execution/cancellation attribution remains unresolved. Any nonzero estimate must be labeled a conditional diagnostic, with assumptions about deletion, partial reductions, matching phase, hidden liquidity, and priority stated explicitly. An optimistic depletion scenario must still require enough subsequent same-price execution-assumed quantity to consume the virtual unit after the ahead queue has cleared. Changes at unrelated prices cannot fill it.

Differences between two chosen priority scenarios are sensitivity results; they must not be called mathematical bounds over every possible hidden matching process. Conditional post-fill markouts for a zero-fill lower bound are undefined, never zero. A complete study must retain this identification limit even if optimistic diagnostics look favorable.
