# Q4 Transformer gate: skipped

The roadmap's conditional Transformer trigger was evaluated from the immutable Q2/Q3 aggregate receipts in `results/sequence_ml_v1/q4_gate.json`. This is a retrospective gate, not an independent-final model verdict.

- GRU seed-mean minus April-selected historical XGBoost: +0.006110 IC, above the predeclared planning threshold +0.005.
- Three seed-specific means are positive; June, September and November differences are positive; removing any one stock leaves a positive overall mean. Q1 sequence and Q3 crossing identity tests passed within their stated contracts.
- **Training adequacy fails the gate.** Q2 KGHM seeds 17 and 29 reached epoch 15 with best dev loss at the cap. Q3 rolling refits retained eight further capped seed/stock/month fits across five cells. Those flags cannot be erased because the historical IC happened to be positive.

Decision: **`SKIP_TRANSFORMER`**. No S1 configuration was searched or trained, and no Transformer claim is made. The correct continuation is Q5 data qualification, then the final bounded package. Revising the original training protocol merely to obtain a desired Q4 trigger would make the old-sample selection less credible.
