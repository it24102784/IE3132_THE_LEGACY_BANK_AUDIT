# THE LEGACY BANK AUDIT - CTF Play Box

## SLIIT IE3132 Penetration Testing (Year 3, Semester 1 - 2026)

**Assignment 01 - Group 78**

---

## 1. Project Overview

"THE LEGACY BANK AUDIT" is a Docker-based Capture The Flag (CTF) Play Box environment simulating an authorized red-team security assessment of an old financial staging server left exposed during a cloud migration.

The architecture strictly follows security isolation principles:

- **Control Layer (`dashboard`)**: The single entry point exposed to the host machine.
- **Challenge Targets (`web_challenge` & `linux_challenge`)**: Isolated on a private Docker bridge network (`ctf_isolated_net`) with no public internet access or direct host port exposures.

---

## 2. Architecture & Service Components

| Service Name          | Description                            | Host Access             | Internal IP   | Container Port | Health Check         |
| :-------------------- | :------------------------------------- | :---------------------- | :------------ | :------------- | :------------------- |
| **`dashboard`**       | CTF Control Layer & Dashboard          | Port `5000`             | `10.10.10.2`  | `5000`         | HTTP `/health`       |
| **`dashboard`**       | CTF Control Layer & Dashboard          | Port `5001`             | `10.10.10.2`  | `80`           | HTTP `/health`       |
| **`kali_player`**     | Stage 1 network tools (`nmap`, `curl`) | Isolated                | `10.10.10.3`  | N/A            | Persistent shell     |
| **`web_challenge`**   | Legacy Employee Portal Target          | `127.0.0.1:8082` only   | `10.10.10.5`  | `80`           | HTTP `/health`       |
| **`linux_challenge`** | Legacy Linux Server Target             | Isolated (No Host Port) | `10.10.10.10` | `22`           | `/tmp/healthy` check |

---

## 3. Security & Isolation Constraints

- **Private Docker Network**: Uses `ctf_isolated_net` (`10.10.10.0/24`) with `internal: true`.
- **Zero Privilege Escalation to Host**: Containers do **not** run in privileged mode (`privileged: false`).
- **No Host Mounts**: No host filesystems or Docker sockets (`/var/run/docker.sock`) are mounted.
- **Minimal Exposure**: Only the `dashboard` control layer port (`5000`) is mapped to the host interface.
- **Non-Root Containers**: Web and Dashboard containers execute as non-root unprivileged users (`ctfuser`).
- **Windows Compatibility**: Tested and optimized for Windows Docker Desktop (Linux Containers mode).

---

## 4. Deployment & Quick Start Guide

### Prerequisites

- **Docker Desktop** installed on Windows (with Linux Containers backend enabled).
- **Docker Compose** v2+ enabled.

### Step-by-step Setup Instructions

1. **Clone or navigate to the repository directory**:

   ```bash
   cd legacy-bank-ctf
   ```

2. **Initialize Environment Variables**:
   Copy the example environment file:

   ```cmd
   copy .env.example .env
   ```

   _(On PowerShell or Bash: `cp .env.example .env`)_

3. **Build and Launch Containers**:

   ```bash
   docker compose up -d --build
   ```

4. **Verify Service Health & Status**:
   Check container status and health check status:

   ```bash
   docker compose ps
   ```

5. **Access the CTF Control Dashboard**:
   Open your browser and navigate to:
   [http://localhost:5001](http://localhost:5001)

6. **Use the Stage 1 network tools**:
   The `10.10.10.0/24` challenge network is private to Docker. Run network
   scans from the bundled player container, not from a Kali/WSL host shell:

   ```bash
   docker compose exec kali_player bash
   ```
   Then, at the player-container prompt, run:

   ```bash
   nmap -sn 10.10.10.0/24
   nmap -Pn -sV -p 80 10.10.10.5
   curl -sSI http://10.10.10.5/
   ```

   The player container stays running with the Compose stack and includes
   `nmap` and `curl`. From the Windows/WSL host, the web target is reachable
   only through its loopback-published port:

   ```bash
   curl -sSI http://localhost:8082/
   ```

   Do not scan `10.10.10.5` from the host; that address is only reachable
   inside the Docker network.

---

## 5. Basic Health Verification Commands

- **Check Dashboard Endpoint (Host)**:

  ```bash
  curl http://localhost:5000/health
  ```

  _Expected Output_: `{"service":"dashboard","status":"healthy"}`

- **Inspect Container Logs**:

  ```bash
  docker compose logs dashboard
  docker compose logs web_challenge
  docker compose logs linux_challenge
  ```

- **Stop & Clean Up**:
  ```bash
  docker compose down
  ```
