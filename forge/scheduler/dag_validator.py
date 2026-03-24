"""Static DAG validator — runs after VisionCompiler, before ForgeScheduler.

Checks for structural problems and common LLM mistakes.
Issues are returned as warnings; the caller decides whether to abort or proceed.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from forge.compiler.schema import ProductionPlan

# Motion verbs that imply pixel-level continuity between scenes
_MOTION_VERBS = {
    "walks", "walk", "walking",
    "runs", "run", "running",
    "enters", "enter", "entering",
    "sits", "sit", "sitting",
    "stands", "stand", "standing",
    "picks", "pick", "picking",
    "opens", "open", "opening",
    "closes", "close", "closing",
    "falls", "fall", "falling",
    "fights", "fight", "fighting",
    "chases", "chase", "chasing",
    "grabs", "grab", "grabbing",
    "turns", "turn", "turning",
    "reaches", "reach", "reaching",
}


@dataclass
class ValidationIssue:
    level: str  # "error" | "warning"
    rule: str
    message: str
    auto_fixed: bool = False


@dataclass
class DAGValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.level == "error" for i in self.issues)

    def summary(self) -> str:
        errors = sum(1 for i in self.issues if i.level == "error")
        warnings = sum(1 for i in self.issues if i.level == "warning")
        fixed = sum(1 for i in self.issues if i.auto_fixed)
        return (
            f"{errors} error(s), {warnings} warning(s), {fixed} auto-fixed"
        )


def validate_and_fix(plan: ProductionPlan) -> DAGValidationReport:
    """
    Validate the DAG in-place and auto-fix safe issues.
    Returns a report of all findings.
    """
    report = DAGValidationReport()
    scene_ids = {s.id for s in plan.scenes}
    dag = plan.dag

    # ── Rule 1: All DAG nodes must reference existing scenes ──────────────
    for src, dsts in list(dag.items()):
        if src not in scene_ids:
            report.issues.append(ValidationIssue(
                level="error", rule="unknown_node",
                message=f"DAG node {src!r} not in scenes list",
            ))
        for dst in dsts:
            if dst not in scene_ids:
                report.issues.append(ValidationIssue(
                    level="error", rule="unknown_node",
                    message=f"DAG edge {src!r} -> {dst!r}: {dst!r} not in scenes list",
                ))

    # ── Rule 2: No cycles ──────────────────────────────────────────────────
    try:
        from forge.scheduler.dag import topological_sort
        topological_sort(dag)
    except ValueError:
        report.issues.append(ValidationIssue(
            level="error", rule="cycle",
            message="DAG contains a cycle — cannot schedule",
        ))

    # ── Rule 3: Suspicious all-parallel (no edges at all) ─────────────────
    total_edges = sum(len(v) for v in dag.values())
    if total_edges == 0 and len(plan.scenes) > 2:
        report.issues.append(ValidationIssue(
            level="warning", rule="all_parallel",
            message=(
                f"All {len(plan.scenes)} scenes are parallel (no DAG edges). "
                "LLM may have skipped dependency analysis."
            ),
        ))

    # ── Rule 4: Consecutive scenes with motion verbs → auto-add edge ──────
    scenes_sorted = plan.scenes  # narrative order as returned by LLM
    for i in range(len(scenes_sorted) - 1):
        a = scenes_sorted[i]
        b = scenes_sorted[i + 1]

        # Check if b already depends on a
        already_depends = b.id in dag.get(a.id, [])
        if already_depends:
            continue

        # Check if a's description ends with a motion verb
        a_words = set(a.description.lower().split())
        b_words = set(b.description.lower().split())
        motion_in_a = bool(a_words & _MOTION_VERBS)
        motion_in_b = bool(b_words & _MOTION_VERBS)

        # Check same assets_required overlap (same character)
        shared_assets = set(a.assets_required) & set(b.assets_required)

        if shared_assets and (motion_in_a or motion_in_b):
            # Auto-fix: add the edge
            if a.id not in dag:
                dag[a.id] = []
            if b.id not in dag[a.id]:
                dag[a.id].append(b.id)
            report.issues.append(ValidationIssue(
                level="warning",
                rule="missing_continuity_edge",
                message=(
                    f"Auto-added edge {a.id!r} -> {b.id!r}: "
                    f"shared assets {shared_assets} + motion verbs detected"
                ),
                auto_fixed=True,
            ))

    # ── Rule 5: Isolated interior nodes ───────────────────────────────────
    has_outgoing = {src for src, dsts in dag.items() if dsts}
    has_incoming = {dst for dsts in dag.values() for dst in dsts}
    for s in plan.scenes[1:-1]:  # skip first and last
        if s.id not in has_outgoing and s.id not in has_incoming:
            report.issues.append(ValidationIssue(
                level="warning", rule="isolated_node",
                message=(
                    f"Scene {s.id!r} is isolated (no edges). "
                    "Verify it doesn't need continuity with neighbors."
                ),
            ))

    return report
