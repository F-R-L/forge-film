import pytest
from forge.compiler.schema import Asset, AssetType, ProductionPlan, Scene
from forge.scheduler.dag_validator import validate_and_fix


def make_plan(
    scene_ids: list[str],
    dag: dict[str, list[str]],
    descriptions: dict[str, str] | None = None,
    assets: list[Asset] | None = None,
    asset_refs: dict[str, list[str]] | None = None,
) -> ProductionPlan:
    scenes = [
        Scene(
            id=sid,
            description=(descriptions or {}).get(sid, "A scene."),
            complexity=3,
            estimated_duration_sec=10.0,
            assets_required=(asset_refs or {}).get(sid, []),
        )
        for sid in scene_ids
    ]
    return ProductionPlan(
        title="Test",
        scenes=scenes,
        assets=assets or [],
        dag=dag,
    )


def test_valid_plan_no_issues():
    plan = make_plan(["S1", "S2"], {"S1": ["S2"], "S2": []})
    report = validate_and_fix(plan)
    assert not report.has_errors
    assert report.issues == []


def test_unknown_dag_node_raises_error():
    plan = make_plan(["S1", "S2"], {"S1": ["S99"], "S2": []})
    report = validate_and_fix(plan)
    assert report.has_errors
    error_rules = [i.rule for i in report.issues]
    assert "unknown_node" in error_rules


def test_cycle_detected_as_error():
    plan = make_plan(["S1", "S2"], {"S1": ["S2"], "S2": ["S1"]})
    report = validate_and_fix(plan)
    assert report.has_errors
    error_rules = [i.rule for i in report.issues]
    assert "cycle" in error_rules


def test_self_loop_raises_error():
    plan = make_plan(["S1", "S2"], {"S1": ["S1"], "S2": []})
    report = validate_and_fix(plan)
    assert report.has_errors
    error_rules = [i.rule for i in report.issues]
    assert "self_loop" in error_rules


def test_isolated_interior_node_warns():
    # S1, S2, S3 — S2 is interior but has no edges
    plan = make_plan(
        ["S1", "S2", "S3"],
        {"S1": [], "S2": [], "S3": []},
    )
    report = validate_and_fix(plan)
    assert not report.has_errors
    warn_rules = [i.rule for i in report.issues]
    assert "isolated_node" in warn_rules


def test_missing_continuity_edge_auto_fixed():
    """Two adjacent scenes sharing an asset + motion verb should get an auto-added edge."""
    asset = Asset(id="char_a", type=AssetType.CHARACTER, description="Hero")
    plan = make_plan(
        ["S1", "S2"],
        {"S1": [], "S2": []},
        descriptions={"S1": "Hero walks into the room.", "S2": "Hero sits down."},
        assets=[asset],
        asset_refs={"S1": ["char_a"], "S2": ["char_a"]},
    )
    report = validate_and_fix(plan)
    fixed = [i for i in report.issues if i.auto_fixed]
    assert any(i.rule == "missing_continuity_edge" for i in fixed)
    # Edge should be present in the DAG now
    assert "S2" in plan.dag.get("S1", [])


def test_report_summary_format():
    plan = make_plan(["S1", "S2"], {"S1": ["S99"], "S2": []})
    report = validate_and_fix(plan)
    summary = report.summary()
    assert "error" in summary
    assert "warning" in summary
