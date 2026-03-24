from collections import deque


def build_adjacency(dag: dict[str, list[str]]) -> dict[str, list[str]]:
    """Validate and return the adjacency list (dag is already adjacency format)."""
    all_ids = set(dag.keys())
    for src, dsts in dag.items():
        for dst in dsts:
            if dst not in all_ids:
                raise ValueError(f"DAG references unknown node: {dst!r}")
    return dag


def topological_sort(dag: dict[str, list[str]]) -> list[str]:
    """Kahn's algorithm. Raises ValueError if cycle detected."""
    in_degree = compute_in_degree(dag)
    queue = deque(n for n, d in in_degree.items() if d == 0)
    result = []

    while queue:
        node = queue.popleft()
        result.append(node)
        for downstream in dag.get(node, []):
            in_degree[downstream] -= 1
            if in_degree[downstream] == 0:
                queue.append(downstream)

    if len(result) != len(dag):
        raise ValueError("DAG contains cycle")
    return result


def compute_in_degree(dag: dict[str, list[str]]) -> dict[str, int]:
    """Compute in-degree for each node (how many nodes point TO it)."""
    in_degree = {node: 0 for node in dag}
    for src, dsts in dag.items():
        for dst in dsts:
            in_degree[dst] = in_degree.get(dst, 0) + 1
    # Ensure all nodes referenced as destinations are in the dict
    for node in list(in_degree.keys()):
        if node not in dag:
            dag[node] = []
    return in_degree


def get_reverse_dag(dag: dict[str, list[str]]) -> dict[str, list[str]]:
    """Return reverse adjacency list (upstream -> downstream becomes downstream -> upstream)."""
    reverse: dict[str, list[str]] = {node: [] for node in dag}
    for src, dsts in dag.items():
        for dst in dsts:
            reverse[dst].append(src)
    return reverse
