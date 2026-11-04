# TLS Certificate Setup Guide

EnviroMesh secures communication between RPi 1 (Gateway) and RPi 2 (Core) using **MQTT over TLS (port 8883)**. This prevents eavesdropping, tampering, and unauthorized data injection across the local network.

---

## 1. Overview of PKI Architecture

- **Certificate Authority (CA)**: Self-signed root CA created on RPi 2.
- **Server Certificate**: Issued by the root CA to RPi 2's EMQX broker. Matches the RPi 2 IP/hostname in its Subject Alternative Names (SAN).
- **Client (Gateway)**: RPi 1 uses `ca.crt` to verify the authenticity of RPi 2's EMQX broker before transmitting telemetry.

---

## 2. Generating Certificates on RPi 2 (Core)

Run these commands on **RPi 2**:

```bash
mkdir -p ./EnviroMesh/raspberry_pi/core/emqx/certs
cd ./EnviroMesh/raspberry_pi/core/emqx/certs

# 1. Generate CA private key and self-signed certificate (valid 10 years)
openssl genrsa -out ca.key 4096
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 -out ca.crt \
    -subj "/C=FR/ST=IDF/L=Paris/O=EnviroMesh/CN=EnviroMesh-Root-CA"

# 2. Generate Server private key and CSR
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr \
    -subj "/C=FR/ST=IDF/L=Paris/O=EnviroMesh/CN=192.168.1.5"

# 3. Create extension file for Subject Alternative Names (SAN)
# Replace 192.168.1.5 with your actual RPi 2 IP address or hostname
cat > server_ext.cnf <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment
subjectAltName = @alt_names

[alt_names]
IP.1 = 192.168.1.5
IP.2 = 127.0.0.1
DNS.1 = rpi2-core.local
DNS.2 = localhost
EOF

# 4. Sign the Server certificate with the CA
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out server.crt -days 3650 -sha256 -extfile server_ext.cnf

# 5. Restrict permissions on private keys
chmod 600 ca.key server.key
chmod 644 ca.crt server.crt
```

---

## 3. Copying CA Certificate to RPi 1 (Gateway)

RPi 1 only requires `ca.crt` to validate RPi 2. Never transfer private keys to RPi 1.

From RPi 2 (or via SCP from your workstation):

```bash
scp ./EnviroMesh/raspberry_pi/core/emqx/certs/ca.crt \
    user@192.168.1.20:./EnviroMesh/raspberry_pi/gateway/certs/core-ca.crt
```

Ensure permissions on RPi 1:

```bash
chmod 644 ./EnviroMesh/raspberry_pi/gateway/certs/core-ca.crt
```

---

## 4. Verification

Test the TLS connection using OpenSSL from RPi 1:

```bash
openssl s_client -connect 192.168.1.5:8883 -CAfile certs/core-ca.crt
```

If successful, the output will display:
```
Verify return code: 0 (ok)
```

