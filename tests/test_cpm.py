from forge.scheduler.cpm import compute_critical_path, get_priority_queue_items


def test_cpm_linear():
    # S1(30) -> S2(60) -> S3(90)
    dag = {"S1": ["S2"], "S2": ["S3"], "S3": []}
    durations = {"S1": 30.0, "S2": 60.0, "S3": 90.0}
    cp = compute_critical_path(dag, durations)
    # S1's critical path remaining = 30 + 60 + 90 = 180
    assert cp["S1"] == 180.0
    assert cp["S2"] == 150.0
    assert cp["S3"] == 90.0


def test_cpm_parallel():
    # S1(30)->S3(90), S2(60)->S3(90)
    dag = {"S1": ["S3"], "S2": ["S3"], "S3": []}
    durations = {"S1": 30.0, "S2": 60.0, "S3": 90.0}
    cp = compute_critical_path(dag, durations)
    # S2 has longer path: 60+90=150 vs S1: 30+90=120
    assert cp["S2"] > cp["S1"]
    assert cp["S2"] == 150.0
    assert cp["S1"] == 120.0
    assert cp["S3"] == 90.0


def test_cpm_single_node():
    dag = {"S1": []}
    durations = {"S1": 45.0}
    cp = compute_critical_path(dag, durations)
    assert cp["S1"] == 45.0


def test_priority_queue_items():
    cp = {"S1": 180.0, "S2": 150.0}
    items = get_priority_queue_items(cp)
    # Should be negative for min-heap (higher priority = more negative)
    assert (-180.0, "S1") in items
    assert (-150.0, "S2") in items
