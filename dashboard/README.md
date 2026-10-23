# Dashboard — Environmental Monitoring System

The dashboard is the user-facing web application of the EnviroMesh platform. It
provides authentication, role-based access control (RBAC), and real-time
visualization of environmental telemetry collected from the field sensor nodes.

## Role in the Architecture

Per the project architecture (`../README.md`), the dashboard connects to
**RPi 2 (Core Processing Server)** over **HTTPS / WebSockets**. RPi 2 hosts the
databases (PostgreSQL + TimescaleDB), the MQTT broker, the video proxy, and
RBAC authentication. The dashboard consumes telemetry and alerts from this core
server and presents them to operators filtered by their assigned zones and roles.

## Features

- **Authentication:** Email/password login with JWT-based sessions (RBAC: `admin` / `zone_technician`).
- **Real-time telemetry:** Live charts of sensor readings (gas, temperature, humidity, water leak, pressure, motion) streamed via WebSockets.
- **Zone filtering:** Users only see devices and data belonging to their assigned group/zone.
- **Device status:** Overview of all edge nodes (G11, G41, G31, G61) with online/offline and maintenance status.
- **Video streaming:** RTSP video proxy integration (ESP32-CAM via MediaMTX on RPi 2).
- **Actuation:** Secure BLE control of the micro servo (0°–180°) on the G61 servo node.

## Directory Layout

```
dashboard/
├── README.md            # This file
├── src/                 # Frontend source code (React / web UI)
├── public/              # Static assets
└── ...                  # Configuration, build files, etc.
```

*(Populate `src/`, `public/`, and config files as the UI is implemented in Phase 4 of the roadmap.)*

## Implementation Roadmap (Phase 4)

As outlined in the project README, the dashboard is built in **Phase 4: Dashboard & Security Layer**:

1. Build the web UI with email/password login.
2. Connect Grafana or a custom React dashboard to display real-time time-series charts filtered by user roles.
3. Integrate with the MQTT broker and WebSocket endpoints on RPi 2.
4. Enforce RBAC claims inside signed JWT tokens and topic-level permissions on the MQTT broker.

## Related Documentation

- Project architecture & full specification: [`../README.md`](../README.md)
- Database layer: [`../db`](../db)
- Firmware nodes: [`../firmware`](../firmware)

## Resources

- [IoT Architecture](https://www.kaaiot.com/iot-knowledge-base/visualizing-iot-architecture-with-diagrams)
- [Diagrams.net](https://app.diagrams.net/)
