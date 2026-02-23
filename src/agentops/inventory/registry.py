"""
Infrastructure Inventory — device registry, topology map, service
dependencies, and maintenance windows.

The inventory is the source of truth for what exists in the
infrastructure and how it's connected.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DeviceType(str, Enum):
    """Infrastructure device types."""
    SERVER = "server"
    ROUTER = "router"
    SWITCH = "switch"
    FIREWALL = "firewall"
    LOAD_BALANCER = "load_balancer"
    DATABASE = "database"
    STORAGE = "storage"
    CONTAINER_HOST = "container_host"


class DeviceStatus(str, Enum):
    """Device operational status."""
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    DEGRADED = "degraded"
    DOWN = "down"
    DECOMMISSIONED = "decommissioned"


@dataclass
class Device:
    """An infrastructure device."""
    device_id: str
    name: str
    device_type: DeviceType
    status: DeviceStatus = DeviceStatus.ACTIVE
    location: str = ""
    ip_address: str = ""
    os_version: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    services: list[str] = field(default_factory=list)
    registered_at: float = field(default_factory=time.time)


@dataclass
class ServiceDependency:
    """A dependency between two services."""
    source_service: str
    target_service: str
    dependency_type: str = "hard"  # hard, soft
    description: str = ""


@dataclass
class MaintenanceWindow:
    """A scheduled maintenance window."""
    window_id: str
    device_ids: list[str]
    start_time: float
    end_time: float
    description: str = ""
    approved_by: str = ""


class DeviceRegistry:
    """
    Infrastructure device registry with topology and dependency tracking.
    """

    def __init__(self) -> None:
        self.devices: dict[str, Device] = {}
        self.topology: dict[str, list[str]] = {}  # device_id -> [connected_device_ids]
        self.service_deps: list[ServiceDependency] = []
        self.maintenance_windows: list[MaintenanceWindow] = []

    def register_device(self, device: Device) -> None:
        """Register a new device."""
        self.devices[device.device_id] = device
        if device.device_id not in self.topology:
            self.topology[device.device_id] = []

    def remove_device(self, device_id: str) -> None:
        """Remove a device from the registry."""
        self.devices.pop(device_id, None)
        self.topology.pop(device_id, None)
        for neighbors in self.topology.values():
            if device_id in neighbors:
                neighbors.remove(device_id)

    def add_connection(self, device_a: str, device_b: str) -> None:
        """Add a bidirectional connection between two devices."""
        if device_a not in self.topology:
            self.topology[device_a] = []
        if device_b not in self.topology:
            self.topology[device_b] = []
        if device_b not in self.topology[device_a]:
            self.topology[device_a].append(device_b)
        if device_a not in self.topology[device_b]:
            self.topology[device_b].append(device_a)

    def get_neighbors(self, device_id: str) -> list[Device]:
        """Get all directly connected devices."""
        neighbor_ids = self.topology.get(device_id, [])
        return [self.devices[nid] for nid in neighbor_ids if nid in self.devices]

    def get_blast_radius(self, device_id: str, depth: int = 2) -> list[str]:
        """Calculate blast radius — devices affected if this one fails."""
        visited = set()
        queue = [(device_id, 0)]

        while queue:
            current, current_depth = queue.pop(0)
            if current in visited or current_depth > depth:
                continue
            visited.add(current)
            for neighbor in self.topology.get(current, []):
                if neighbor not in visited:
                    queue.append((neighbor, current_depth + 1))

        visited.discard(device_id)
        return list(visited)

    def is_in_maintenance(self, device_id: str) -> bool:
        """Check if a device is currently in a maintenance window."""
        now = time.time()
        for window in self.maintenance_windows:
            if device_id in window.device_ids:
                if window.start_time <= now <= window.end_time:
                    return True
        return False

    def add_service_dependency(self, source: str, target: str, dep_type: str = "hard") -> None:
        """Add a service dependency."""
        self.service_deps.append(ServiceDependency(
            source_service=source,
            target_service=target,
            dependency_type=dep_type,
        ))

    def get_service_dependencies(self, service_name: str) -> list[str]:
        """Get all services that a given service depends on."""
        return [d.target_service for d in self.service_deps if d.source_service == service_name]

    def get_dependent_services(self, service_name: str) -> list[str]:
        """Get all services that depend on a given service."""
        return [d.source_service for d in self.service_deps if d.target_service == service_name]

    def get_inventory_summary(self) -> dict[str, Any]:
        """Get a summary of the full inventory."""
        type_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        for device in self.devices.values():
            type_counts[device.device_type.value] = type_counts.get(device.device_type.value, 0) + 1
            status_counts[device.status.value] = status_counts.get(device.status.value, 0) + 1

        return {
            "total_devices": len(self.devices),
            "by_type": type_counts,
            "by_status": status_counts,
            "total_connections": sum(len(v) for v in self.topology.values()) // 2,
            "service_dependencies": len(self.service_deps),
            "maintenance_windows": len(self.maintenance_windows),
        }

    def setup_demo_inventory(self) -> None:
        """Create a demo infrastructure inventory."""
        devices = [
            Device("core-rtr-01", "Core Router 1", DeviceType.ROUTER, ip_address="10.0.0.1", location="DC-1", services=["routing", "bgp"]),
            Device("core-rtr-02", "Core Router 2", DeviceType.ROUTER, ip_address="10.0.0.2", location="DC-1", services=["routing", "bgp"]),
            Device("dist-sw-01", "Distribution Switch 1", DeviceType.SWITCH, ip_address="10.0.1.1", location="DC-1"),
            Device("dist-sw-02", "Distribution Switch 2", DeviceType.SWITCH, ip_address="10.0.1.2", location="DC-1"),
            Device("web-srv-01", "Web Server 1", DeviceType.SERVER, ip_address="10.0.10.1", location="DC-1", services=["nginx", "app"]),
            Device("web-srv-02", "Web Server 2", DeviceType.SERVER, ip_address="10.0.10.2", location="DC-1", services=["nginx", "app"]),
            Device("db-srv-01", "Database Primary", DeviceType.DATABASE, ip_address="10.0.20.1", location="DC-1", services=["postgresql"]),
            Device("db-srv-02", "Database Replica", DeviceType.DATABASE, ip_address="10.0.20.2", location="DC-1", services=["postgresql"]),
            Device("fw-01", "Firewall 1", DeviceType.FIREWALL, ip_address="10.0.0.254", location="DC-1", services=["firewall"]),
            Device("lb-01", "Load Balancer", DeviceType.LOAD_BALANCER, ip_address="10.0.0.100", location="DC-1", services=["haproxy"]),
        ]

        for device in devices:
            self.register_device(device)

        # Build topology
        connections = [
            ("core-rtr-01", "core-rtr-02"),
            ("core-rtr-01", "dist-sw-01"),
            ("core-rtr-02", "dist-sw-02"),
            ("core-rtr-01", "fw-01"),
            ("core-rtr-02", "fw-01"),
            ("dist-sw-01", "web-srv-01"),
            ("dist-sw-01", "web-srv-02"),
            ("dist-sw-02", "db-srv-01"),
            ("dist-sw-02", "db-srv-02"),
            ("dist-sw-01", "lb-01"),
            ("dist-sw-02", "lb-01"),
        ]
        for a, b in connections:
            self.add_connection(a, b)

        # Service dependencies
        self.add_service_dependency("app", "postgresql", "hard")
        self.add_service_dependency("nginx", "app", "hard")
        self.add_service_dependency("haproxy", "nginx", "hard")
        self.add_service_dependency("app", "routing", "hard")
