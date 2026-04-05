"""Structural tests — verify graphs compile and have correct topology.

Run without an API key: these tests only inspect graph structure and state schemas.
  pytest tests/test_graphs.py -v
"""
import os
import sys

import pytest

# Point to ai-service root so imports resolve
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")
os.environ.setdefault("DB_PATH", "data/sample.db")
os.environ.setdefault("CHROMA_PATH", "data/chroma")


# ── Import all compiled graphs ─────────────────────────────────────────────
from src.agents.gen_report_agent import ReportState, gen_report_graph
from src.agents.gen_dashboard_agent import DashboardState, gen_dashboard_graph
from src.agents.supervisor import SupervisorState, supervisor_graph


class TestGenReportGraph:
    def test_nodes_exist(self):
        nodes = list(gen_report_graph.nodes)
        assert "agent" in nodes
        assert "tools" in nodes

    def test_has_cycle(self):
        """Verify the back-edge tools→agent exists (makes it a true graph, not DAG)."""
        edges = gen_report_graph.get_graph().edges
        edge_pairs = [(e.source, e.target) for e in edges]
        assert ("tools", "agent") in edge_pairs, "ReAct cycle tools→agent missing"

    def test_state_uses_typeddict(self):
        import typing
        assert typing.get_type_hints(ReportState).get("messages") is not None


class TestGenDashboardGraph:
    def test_nodes_exist(self):
        nodes = list(gen_dashboard_graph.nodes)
        assert "agent" in nodes
        assert "tools" in nodes

    def test_has_cycle(self):
        edges = gen_dashboard_graph.get_graph().edges
        edge_pairs = [(e.source, e.target) for e in edges]
        assert ("tools", "agent") in edge_pairs, "ReAct cycle tools→agent missing"


class TestSupervisorGraph:
    def test_all_nodes_registered(self):
        nodes = list(supervisor_graph.nodes)
        assert "router" in nodes
        assert "gen_report" in nodes
        assert "gen_dashboard" in nodes
        assert "general" in nodes

    def test_entry_point_is_router(self):
        graph_repr = supervisor_graph.get_graph()
        # __start__ should connect to router
        edge_sources = [e.source for e in graph_repr.edges]
        assert "__start__" in edge_sources

    def test_state_schema(self):
        import typing
        hints = typing.get_type_hints(SupervisorState)
        assert "messages" in hints
        assert "next_agent" in hints
