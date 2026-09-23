import numpy as np
import pytest

from cloblab.polymarket_models import market_equal_weights, market_scores, market_paired_bootstrap


def test_market_equal_weights_prevent_dense_market_dominance():
    markets=np.asarray(['a','a','a','b'])
    weights=market_equal_weights(markets)
    assert weights[:3].sum()==pytest.approx(weights[3])
    assert weights.mean()==pytest.approx(1)


def test_market_scores_average_within_then_across_markets():
    labels=np.asarray([1,1,1,0])
    pred=np.asarray([.9,.9,.9,.1])
    markets=np.asarray(['a','a','a','b'])
    result=market_scores(labels,pred,markets,1e-4)
    assert result['markets']==2 and result['opportunities']==4
    assert result['market_mean_log_loss']==pytest.approx(-np.log(.9))
    with pytest.raises(ValueError,match='terminal labels'):
        market_scores(np.asarray([1,0]),np.asarray([.9,.1]),np.asarray(['a','a']),1e-4)


def test_paired_bootstrap_preserves_market_identities():
    first={'a':.4,'b':.5,'c':.6}
    second={'a':.3,'b':.4,'c':.5}
    result=market_paired_bootstrap(first,second,seed=7,draws=100)
    assert result['market_mean_delta']==pytest.approx(-.1)
    assert result['paired_markets']==3 and result['negative_market_differences']==3
    with pytest.raises(ValueError,match='identities'):
        market_paired_bootstrap(first,{'a':.3},seed=7,draws=100)
