# FI-2010 source and license evidence

Checked September 14, 2026 UTC, before dataset use.

- Authoritative record: https://etsin.fairdata.fi/dataset/73eb48d7-4dbc-4a10-a52a-da745b47a649
- Persistent identifier: urn:nbn:fi:csc-kata20170601153214969115
- Title: Benchmark Dataset for Mid-Price Forecasting of Limit Order Book Data with Machine Learning Methods.
- Rights holder in the record: BigDataFinance.
- Authors: Adamantios Ntakaris, Martin Magris, Juho Kanniainen, Moncef Gabbouj, Alexandros Iosifidis.
- License: Creative Commons Attribution 4.0 International (CC BY 4.0).
- Exact legal text: https://creativecommons.org/licenses/by/4.0/legalcode.en
- Official record access type: Open. The same license is present in the rendered
  license field and the page's `initial-dataset` metadata (`access_rights.license`).
- Original paper: https://arxiv.org/abs/1705.03233 ; published citation:
  Ntakaris et al. (2018), Journal of Forecasting, DOI 10.1002/for.2543.

CC BY 4.0 sections 2 and 3 permit reproduction, sharing and adaptation with
attribution, license notice/link and identification of modifications. There is
no ML-specific restriction in this license. Together with the official record's
explicit ML benchmark purpose, this supports research model fitting and
publication of derived aggregate results under those conditions. The license
does not grant unrelated trademark or endorsement rights.

Required attribution on published derived results: credit the five authors,
name FI-2010 and link its official record and CC BY 4.0; identify feature
construction, event-horizon labels and evaluation as this project's modifications.
Acknowledge the original H2020 BigDataFinance MSCA-ITN-ETN 675044 support.

The official record describes 144 feature rows followed by five classification
label rows, normalized using z-score, min-max or decimal precision; nine
anchored day folds combine five stocks. This is not proof that individual
stock boundaries or unscaled prices are available in every distributed file.
Those representation details must be established before deriving new labels.
Raw archives and extracted files remain under git-ignored `data/raw/`.

The paper's sections 3.3–3.4 additionally describe ten-event representations
and feature-dependent decimal scaling. Decimal normalization alone does not
establish preserved cross-feature price/size ratios. Confirm scaling and stock
boundaries before calculating economic markouts, and distinguish observation
offsets from underlying exchange-event counts.
