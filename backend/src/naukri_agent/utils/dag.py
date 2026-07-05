"""
Directed Acyclic Graph (DAG) and Topological Sort implementation.
"""

from __future__ import annotations

from collections import defaultdict, deque


class DAG:
    """Models a Directed Acyclic Graph to manage and sort dependencies."""

    def __init__(self) -> None:
        self.adjacency: dict[str, set[str]] = defaultdict(set)
        self.in_degree: dict[str, int] = defaultdict(int)
        self.nodes: set[str] = set()

    def add_node(self, node: str) -> None:
        """Add a node to the graph if it doesn't exist."""
        self.nodes.add(node)

    def add_edge(self, u: str, v: str) -> None:
        """
        Add a directed edge u -> v (u depends on or must precede v).
        """
        self.add_node(u)
        self.add_node(v)
        if v not in self.adjacency[u]:
            self.adjacency[u].add(v)
            self.in_degree[v] += 1

    def topological_sort(self) -> list[str]:
        """
        Perform a topological sort using Kahn's algorithm.
        Returns the sorted list of nodes.
        Raises ValueError if a cycle is detected.
        """
        in_deg = {node: self.in_degree[node] for node in self.nodes}
        queue = deque([node for node in self.nodes if in_deg[node] == 0])
        order = []

        while queue:
            u = queue.popleft()
            order.append(u)
            for v in self.adjacency[u]:
                in_deg[v] -= 1
                if in_deg[v] == 0:
                    queue.append(v)

        if len(order) != len(self.nodes):
            raise ValueError("Dependency cycle detected! The dependency graph must be a DAG.")

        return order
