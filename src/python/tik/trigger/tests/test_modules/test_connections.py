"""Tests for module connections."""

from __future__ import annotations

import pytest


class TestModuleConnections:
    """Test socket/plug connections between modules."""

    def test_connect_base_to_connector(self, guide_session):
        """Base's rootPlug connects to Connector's rootSocket."""
        # Create base module
        base = guide_session.create_module("base", "base_0")
        base.create_guides()
        base.build()

        # Create connector module
        connector = guide_session.create_module("connector", "connector_0")
        connector.create_guides()
        connector.build()

        # Connect connector's rootSocket to base's rootPlug
        guide_session.connect("base_0", "rootPlug", "connector_0", "rootSocket")

        # Verify connection
        assert connector.sockets["rootSocket"].connected_plug is not None

    def test_multiple_connections(self, guide_session):
        """Multiple modules can be connected."""
        base = guide_session.create_module("base", "base_0")
        base.create_guides()
        base.build()

        connector1 = guide_session.create_module("connector", "conn_1")
        connector1.create_guides()
        connector1.build()

        connector2 = guide_session.create_module("connector", "conn_2")
        connector2.create_guides()
        connector2.build()

        # Connect both connectors to base
        guide_session.connect("base_0", "rootPlug", "conn_1", "rootSocket")
        guide_session.connect("base_0", "rootPlug", "conn_2", "rootSocket")

        assert len(guide_session.connections) == 2

    def test_connection_data_serialized(self, guide_session, tmp_path):
        """Connections are serialized in session save."""
        base = guide_session.create_module("base", "base_0")
        base.create_guides()
        base.build()

        connector = guide_session.create_module("connector", "conn_0")
        connector.create_guides()
        connector.build()

        guide_session.connect("base_0", "rootPlug", "conn_0", "rootSocket")

        # Save session
        file_path = tmp_path / "connected.trg"
        guide_session.save(str(file_path))

        # Reload and verify
        import maya.cmds as cmds
        cmds.file(new=True, force=True)

        new_session = guide_session.__class__()
        new_session.load(str(file_path))

        assert len(new_session.connections) == 1
        conn = new_session.connections[0]
        assert conn.parent_module == "base_0"
        assert conn.child_module == "conn_0"


class TestModuleRemoval:
    """Test module removal with connections."""

    def test_remove_module_clears_connections(self, guide_session):
        """Removing a module clears related connections."""
        base = guide_session.create_module("base", "base_0")
        base.create_guides()
        base.build()

        connector = guide_session.create_module("connector", "conn_0")
        connector.create_guides()
        connector.build()

        guide_session.connect("base_0", "rootPlug", "conn_0", "rootSocket")
        assert len(guide_session.connections) == 1

        # Remove connector
        guide_session.remove_module("conn_0")
        assert len(guide_session.connections) == 0