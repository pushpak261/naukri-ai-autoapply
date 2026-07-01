"""
Tests for the DAG and Topological Sort utility.
"""

from __future__ import annotations

import pytest

from src.naukri_agent.utils.dag import DAG


def test_dag_topological_sort() -> None:
    dag = DAG()
    dag.add_edge("A", "B")
    dag.add_edge("B", "C")
    dag.add_edge("A", "D")

    order = dag.topological_sort()

    assert "A" in order
    assert "B" in order
    assert "C" in order
    assert "D" in order
    assert order.index("A") < order.index("B")
    assert order.index("B") < order.index("C")
    assert order.index("A") < order.index("D")


def test_dag_cycle_detection() -> None:
    dag = DAG()
    dag.add_edge("A", "B")
    dag.add_edge("B", "C")
    dag.add_edge("C", "A")

    with pytest.raises(ValueError, match="Dependency cycle detected"):
        dag.topological_sort()
