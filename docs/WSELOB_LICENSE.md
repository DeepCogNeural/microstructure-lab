# WSELOB-2017 permission and input contract

Checked 2026-09-14 UTC before adapter implementation or model fitting.

- Authoritative depositor record: https://data.mendeley.com/datasets/3g4mhdp899/1
- Citation: Marszałek, Adam (2023), WSELOB-2017: The year-long database of limit order books for the five biggest companies listed on the Warsaw Stock Exchange, Mendeley Data, V1, DOI: 10.17632/3g4mhdp899.1.
- Explicit dataset license: CC BY 4.0, https://creativecommons.org/licenses/by/4.0/legalcode.en.
- The record specifically describes microstructure research and forecasting uses.
- The associated authors' paper, Modeling of limit order book data with ordered fuzzy numbers, acknowledges exchange approval to release this open-access dataset. Source: https://www.sciencedirect.com/science/article/pii/S1568494624003296.

CC BY 4.0 permits adaptation and sharing with attribution. The published license
and research purpose support model fitting and publication of derived aggregates;
there is no separate ML restriction in that license. Credit the depositor,
link the record and license, identify modifications, and retain the license's
as-is/no-warranty notice. No endorsement by the author or WSE is implied.

## Selection fixed before results

FI-2010 was the first candidate but its normalization and concatenated-stock
representation have unresolved economic-scale/boundary questions. WSELOB is
selected instead because its depositor supplies explicit instrument IDs, daily
HDF5 keys, nanosecond timestamps and price scaling. This preserves the requested
midpoint-regression experiment, rather than switching to classification.

Use PEKAO (instrument 11322), the smallest distributed stock file, and its first
ten chronological trading days. This is a bounded one-stock benchmark, not a
full-year or cross-stock generalization claim. Selection does not depend on
predictive results. Train on all previous selected days; hold out each next day.

Official file: PEKAO_lob_2017_zlib.h5, 152759953 bytes,
SHA256 3c418a55a492ebe2e39c8513cd7fc7e3e6827dc1a176af09fdcaad9f3485bae6.
Download: https://data.mendeley.com/public-files/datasets/3g4mhdp899/files/63e3f3ab-f562-4389-a740-357446266a6c/file_downloaded.

The depositor's `order_data.ipynb` documents daily keys `/dYYYYMMDD`, the
`symbol_idx` identity, and price = integer `price / 10**price_level`.
Order identities combine order date and ID within the instrument; F clears,
Y retransmits, A adds, M modifies, D deletes. Missing modification values (-1)
retain existing fields, as demonstrated by the depositor's `orderbook2.py`.
Raw downloaded files stay ignored. Only aggregate results and reconstruction
counts are published, with this attribution and modifications notice.
