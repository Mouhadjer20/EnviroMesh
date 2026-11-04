# Network Architecture & Firewall Configuration

## 1. Network Topology

- **Transport**: Trusted Wi-Fi LAN (WPA2/WPA3 Enterprise or Personal) or Ethernet switch.
- **Subnet Example**: `192.168.1.0/24`
- **RPi 1 (Gateway)**: `192.168.1.20` (DHCP reservation or static)
- **RPi 2 (Core)**: `192.168.1.5` (DHCP reservation or static)
- **ESP32 Wi-Fi Nodes**: Dynamic IP via DHCP on same subnet.

> [!WARNING]
> Ensure **Wireless Client Isolation** (AP Isolation) is **DISABLED** on the router/access point. When enabled, Wi-Fi clients cannot communicate with each other, blocking ESP32s from reaching RPi 1 and RPi 1 from reaching RPi 2.

---

## 2. Port Allocation Table

| Host      | Port  | Protocol | Purpose                           | Source / Allowed Clients             |
| --------- | ----- | -------- | --------------------------------- | ------------------------------------ |
| **RPi 1** | 22    | TCP      | SSH administration                | Admin workstation                    |
| **RPi 1** | 1883  | TCP      | Local EMQX MQTT broker            | ESP32 Wi-Fi nodes (`192.168.1.0/24`) |
| **RPi 1** | 18083 | TCP      | Local EMQX Dashboard              | Localhost `127.0.0.1` (SSH tunnel)   |
| **RPi 2** | 22    | TCP      | SSH administration                | Admin workstation                    |
| **RPi 2** | 8883  | TCP/TLS  | Central EMQX TLS                  | RPi 1 Gateway only (`192.168.1.20`)  |
| **RPi 2** | 18083 | TCP      | Central EMQX Dashboard            | Localhost `127.0.0.1` (SSH tunnel)   |
| **RPi 2** | 8080  | TCP      | Nginx Web Proxy (Dashboard + API) | LAN workstations / browsers          |
| **RPi 2** | 5432  | TCP      | TimescaleDB                       | **Internal Docker network only**     |

---

## 3. UFW Firewall Rules

### On RPi 1 (Gateway)

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH
sudo ufw allow 22/tcp

# Allow Wi-Fi ESP32 nodes to publish MQTT
sudo ufw allow from 192.168.1.0/24 to any port 1883 proto tcp

# Enable firewall
sudo ufw enable
```

### On RPi 2 (Core)

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH
sudo ufw allow 22/tcp

# Allow Web Dashboard & API access from LAN
sudo ufw allow from 192.168.1.0/24 to any port 8080 proto tcp

# Allow ONLY RPi 1 Gateway to connect to EMQX TLS port 8883
sudo ufw allow from 192.168.1.20 to any port 8883 proto tcp

# Enable firewall
sudo ufw enable
```

### Docker & UFW Interaction Note

> [!IMPORTANT]
> By default, Docker manipulates `iptables` rules directly and bypasses UFW chains for container ports bound to `0.0.0.0`.
> In our configuration:
> 1. TimescaleDB has no host port bindings.
> 2. EMQX dashboards are bound explicitly to `127.0.0.1`.
> 3. To guarantee packet filtering on public container ports, consider installing `ufw-docker` or setting `DOCKER_OPTS="--iptables=false"`.

