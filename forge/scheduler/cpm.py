import heapq
from forge.scheduler.dag import topological_sort, get_reverse_dag


def compute_critical_path(
    dag: dict[str, list[str]], durations: dict[str, float]
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

    # Critical path remaining = time from EST of this node to project end
    # = duration_of_node + max(critical_path_remaining of successors)
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
