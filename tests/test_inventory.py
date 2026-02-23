"""Tests for infrastructure inventory — devices, topology, dependencies."""

import pytest
from agentops.inventory.registry import DeviceRegistry, Device, DeviceType, DeviceStatus


class TestDeviceRegistry:
    def test_register_device(self):
        reg = DeviceRegistry()
        dev = Device("srv-01", "Server 1", DeviceType.SERVER)
        reg.register_device(dev)
        assert "srv-01" in reg.devices

    def test_remove_device(self):
        reg = DeviceRegistry()
        reg.register_device(Device("srv-01", "Server 1", DeviceType.SERVER))
        reg.remove_device("srv-01")
        assert "srv-01" not in reg.devices

    def test_add_connection(self):
        reg = DeviceRegistry()
        reg.register_device(Device("a", "A", DeviceType.SERVER))
        reg.register_device(Device("b", "B", DeviceType.SERVER))
        reg.add_connection("a", "b")
        assert "b" in reg.topology["a"]
        assert "a" in reg.topology["b"]

    def test_get_neighbors(self):
        reg = DeviceRegistry()
        reg.register_device(Device("a", "A", DeviceType.ROUTER))
        reg.register_device(Device("b", "B", DeviceType.SWITCH))
        reg.register_device(Device("c", "C", DeviceType.SERVER))
        reg.add_connection("a", "b")
        reg.add_connection("a", "c")
        neighbors = reg.get_neighbors("a")
        assert len(neighbors) == 2

    def test_blast_radius(self):
        reg = DeviceRegistry()
        for i in range(5):
            reg.register_device(Device(f"d{i}", f"Device {i}", DeviceType.SERVER))
        reg.add_connection("d0", "d1")
        reg.add_connection("d1", "d2")
        reg.add_connection("d2", "d3")
        reg.add_connection("d3", "d4")
        # depth=2 from d0 should reach d1 and d2
        radius = reg.get_blast_radius("d0", depth=2)
        assert "d1" in radius
        assert "d2" in radius
        assert "d4" not in radius  # too far

    def test_service_dependencies(self):
        reg = DeviceRegistry()
        reg.add_service_dependency("app", "database", "hard")
        reg.add_service_dependency("web", "app", "hard")
        deps = reg.get_service_dependencies("app")
        assert "database" in deps
        dependents = reg.get_dependent_services("app")
        assert "web" in dependents

    def test_demo_inventory(self):
        reg = DeviceRegistry()
        reg.setup_demo_inventory()
        assert len(reg.devices) == 10
        summary = reg.get_inventory_summary()
        assert summary["total_devices"] == 10
        assert summary["total_connections"] > 0

    def test_inventory_summary(self):
        reg = DeviceRegistry()
        reg.register_device(Device("s1", "S1", DeviceType.SERVER))
        reg.register_device(Device("r1", "R1", DeviceType.ROUTER))
        summary = reg.get_inventory_summary()
        assert summary["total_devices"] == 2
        assert "server" in summary["by_type"]
        assert "router" in summary["by_type"]
