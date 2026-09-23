from scripts.evaluate_sequence_ml_fq4_gate import gate


def reports():
    arm=lambda n:f'S0_history_gru_seed{n}'
    fq2={'stage':'FQ2','levels':{'200000':{
        'training_size_per_stock':200000,'evaluation_cells_per_arm':315,
        'undefined_cells':{'dev':[],'evaluation':[]},
        'training_limited':{s:{arm(n):False for n in (7,17,29)} for s in 'ABCDE'},
        'full_denominator_result':{'paired_vs_B1':{
            'S0_seed_mean':{'mean_delta_ic':.006,
                            'month_delta':{'June':.008,'September':-.001,'November':.011},
                            'leave_one_stock_out_delta':{s:.005 for s in 'ABCDE'}},
            **{arm(n):{'mean_delta_ic':.006} for n in (7,17,29)}}}}}}
    fq3={'retrospective_only':True,'updated_fit_cells':15,
         'input_diagnostic_hashes':{s:'x' for s in 'ABCDE'}}
    return fq2,fq3


def test_gate_requires_full_formal_evidence_and_seed_month_stock_consistency():
    fq2,fq3=reports()
    assert gate(fq2,fq3)['gate_triggered']
    fq2['levels']['200000']['full_denominator_result']['paired_vs_B1']['S0_history_gru_seed29']['mean_delta_ic']=-.001
    assert not gate(fq2,fq3)['gate_triggered']
    fq2,fq3=reports()
    fq2['levels']['200000']['training_limited']['A']['S0_history_gru_seed7']=True
    assert not gate(fq2,fq3)['gate_triggered']
    fq2,fq3=reports()
    fq2['levels']['200000']['full_denominator_result']['paired_vs_B1']['S0_seed_mean']['leave_one_stock_out_delta']['A']=-.001
    assert not gate(fq2,fq3)['gate_triggered']
