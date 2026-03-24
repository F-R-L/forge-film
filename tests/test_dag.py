import pytest
from forge.scheduler.dag import (
    topological_sort,
    compute_in_degree,
    build_adjacency,
    get_reverse_dag,
)


def test_topological_sort_basic():
    dag = {"S1": ["S2"], "S2": ["S3"], "S3": []}
    order = topological_sort(dag)
    assert order.index("S1") < order.index("S2")
    assert order.index("S2") < order.index("S3")


def test_topological_sort_parallel():
    dag = {"S1": ["S3"], "S2": ["S3"], "S3": []}
    order = topological_sort(dag)
    assert order.index("S1") < order.index("S3")
    assert order.index("S2") < order.index("S3")


def test_cycle_detection():
    dag = {"S1": ["S2"], "S2": ["S1"]}
    with pytest.raises(ValueError, match="cycle"):
        topological_sort(dag)


def test_in_degree():
    dag = {"S1": ["S3"], "S2": ["S3"], "S3": []}
    in_deg = compute_in_degree(dag)
    assert in_deg["S1"] == 0
    assert in_deg["S2"] == 0
    assert in_deg["S3"] == 2


def test_build_adjacency_invalid_ref():
    dag = {"S1": ["S99"]}
    with pytest.raises(ValueError):
        build_adjacency(dag)


def test_get_reverse_dag():
    dag = {"S1": ["S3"], "S2": ["S3"], "S3": []}
    rev = get_reverse_dag(dag)
    assert set(rev["S3"]) == {"S1", "S2"}
    assert rev["S1"] == []
    assert rev["S2"] == []
