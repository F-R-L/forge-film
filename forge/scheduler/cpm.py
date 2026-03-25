import heapq
from forge.scheduler.dag import topological_sort, get_reverse_dag

# Estimated real-world generation times per backend (seconds)
# Used to improve CPM accuracy when estimated_duration_sec is a story-level guess
BACKEND_DURATION_ESTIMATES: dict[str, float] = {
    "kling_light": 30.0,   # Kling v1 5s clip ~30s API time
    "kling_heavy": 90.0,   # Kling v1.5 Pro 10s clip ~90s API time
    "cogvideo": 120.0,     # CogVideoX local ~120s on consumer GPU
    "seedance": 45.0,      # Seedance estimated
    "wan": 60.0,           # Wan 2.x estimated
    "mock": 1.0,           # Mock pipeline
}


def estimate_duration_by_backend(scene_duration_sec: float, backend: str) -> float:
    """Return a CPM-adjusted duration estimate that accounts for backend latency.

    If backend is known, use the backend constant as a floor (generation time
    dominates over the clip's narrative duration).
    Falls back to scene's estimated_duration_sec if backend unknown.
    """
    backend_time = BACKEND_DURATION_ESTIMATES.get(backend)
    if backend_time is None:
        return scene_duration_sec
    # The actual wall time is dominated by the backend, not the clip length
    return max(scene_duration_sec, backend_time)


def compute_critical_path(
    dag: dict[str, list[str]],
    durations: dict[str, float],
) -> dict[str, float]:
    """
    Compute critical path remaining length for each node.
    Returns {scene_id -> critical_path_remaining}, higher = higher priority.
    """
    topo = topological_sort(dag)
    reverse = get_reverse_dag(dag)

    # Forward pass: earliest finish time
    est: dict[str, float] = {}  # earliest start time
    eft: dict[str, float] = {}  # earliest finish time
    for node in topo:
        predecessors = reverse.get(node, [])
        if predecessors:
            est[node] = max(eft[p] for p in predecessors)
        else:
            est[node] = 0.0
        eft[node] = est[node] + durations.get(node, 0.0)

    total_duration = max(eft.values()) if eft else 0.0

    # Backward pass: latest finish time
    lft: dict[str, float] = {}
    lst: dict[str, float] = {}  # latest start time
    for node in reversed(topo):
        successors = dag.get(node, [])
        if successors:
            lft[node] = min(lst[s] for s in successors)
        else:
            lft[node] = total_duration
        lst[node] = lft[node] - durations.get(node, 0.0)

    # Critical path remaining = duration + max(cp_remaining of successors)
    cp_remaining: dict[str, float] = {}
    for node in reversed(topo):
        successors = dag.get(node, [])
        if successors:
            cp_remaining[node] = durations.get(node, 0.0) + max(
                cp_remaining[s] for s in successors
            )
        else:
            cp_remaining[node] = durations.get(node, 0.0)

    return cp_remaining


def get_priority_queue_items(
    critical_path: dict[str, float]
) -> list[tuple[float, str]]:
    """Return [(-priority, scene_id), ...] for use with heapq (min-heap)."""
    return [(-priority, scene_id) for scene_id, priority in critical_path.items()]


def compute_critical_path_with_routing(
    dag: dict[str, list[str]],
    scenes: list,  # list[Scene]
    routing: dict[str, str],  # scene_type -> backend
) -> dict[str, float]:
    """Compute CPM using backend-aware duration estimates.

    Parameters
    ----------
    dag:     adjacency list
    scenes:  list of Scene objects (need .id, .scene_type, .estimated_duration_sec)
    routing: scene_type -> backend name mapping
    """
    durations: dict[str, float] = {}
    for scene in scenes:
        scene_type_val = scene.scene_type.value if hasattr(scene.scene_type, "value") else str(scene.scene_type)
        backend = routing.get(scene_type_val, routing.get("default", "mock"))
        durations[scene.id] = estimate_duration_by_backend(
            scene.estimated_duration_sec, backend
        )
    return compute_critical_path(dag, durations)
