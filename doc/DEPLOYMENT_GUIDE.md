# NextGenQA - AWS EC2 & CI/CD Deployment Guide

This guide documents the complete end-to-end deployment architecture, AWS setup, and automated CI/CD pipeline for the **Intelligent User Story Generator Service**.

---

## 1. Cloud Architecture Overview

The service is deployed on **AWS EC2** inside an isolated Docker container with local ModernBERT ML model inference, connecting to **Neon Cloud Serverless PostgreSQL** and external cognitive APIs.

```mermaid
flowchart TD
    subgraph Developer_Environment["Developer & CI/CD"]
        Dev["Developer (git push origin deployment)"] -->|Triggers| GHA["GitHub Actions Runner"]
        GHA -->|Stage 1: CI| PyTest["Automated PyTest Suite (70 Tests)"]
        PyTest -->|Pass ✅| SSH_Deploy["Stage 2: CD (SSH Action)"]
    end

    subgraph AWS_Cloud["AWS Cloud (eu-north-1)"]
        subgraph EC2_Instance["AWS EC2 (t3.small - 2GB RAM + 4GB Swap)"]
            DockerCompose["Docker Compose Engine"]
            subgraph Container["FastAPI Container (Port 8001)"]
                App["Uvicorn / FastAPI Backend"]
                Classifier["ModernBERT Utterance Classifier (PyTorch CPU)"]
                RAG["ChromaDB Vector Store (/app/data)"]
            end
            HostModels["Host Model Weights (/home/ubuntu/.../models)"] -.->|Volume Mount| Classifier
        end
    end

    subgraph External_Services["Cloud & Managed Services"]
        NeonDB[("Neon Cloud PostgreSQL (pgvector + SSL)")]
        AzureSpeech["Azure Speech Cognitive Service"]
        GeminiLLM["Google Gemini 2.0 Flash"]
        Jira["Atlassian Jira API"]
    end

    SSH_Deploy -->|SSH (Port 22)| DockerCompose
    App -->|Database Operations| NeonDB
    App -->|Real-time STT / WebSockets| AzureSpeech
    App -->|Story Synthesis & Embeddings| GeminiLLM
    App -->|Ticket Sync| Jira
```

---

## 2. Infrastructure Specifications

| Component | Specification | Description / Notes |
| :--- | :--- | :--- |
| **Cloud Provider** | Amazon Web Services (AWS) | Region: `eu-north-1` (Stockholm) |
| **Compute (EC2)** | `t3.small` (2 vCPU, 2.0 GB RAM) | Burstable CPU, optimized for PyTorch inference |
| **Virtual Memory** | 4.0 GB Swap Space | Prevents OOM crashes during model loading & spikes |
| **Operating System** | Ubuntu Server 24.04 LTS (HVM) | 64-bit x86 architecture |
| **Storage (EBS)** | 25.0 GiB (gp3 SSD) | Container images, host model weights, persistent data |
| **Database** | Neon Cloud Serverless PostgreSQL | PostgreSQL 15+ with `pgvector` extension & SSL |
| **ML Model** | ModernBERT Utterance Classifier | Fine-tuned PyTorch sequence classification model (~600MB) |

---

## 3. Security Groups & Firewall Configuration

The following inbound rules are configured on the AWS EC2 Security Group:

| Protocol | Port Range | Source | Purpose |
| :--- | :--- | :--- | :--- |
| **SSH** | `22` | Anywhere (`0.0.0.0/0`) or Admin IP | Remote server administration |
| **Custom TCP** | `8001` | Anywhere (`0.0.0.0/0`) | FastAPI service & WebSocket endpoints |
| **HTTP** | `80` | Anywhere (`0.0.0.0/0`) | Standard web traffic / Reverse proxy |
| **HTTPS** | `443` | Anywhere (`0.0.0.0/0`) | Secure SSL/TLS endpoints |

---

## 4. Model Storage & Inference Optimization

The fine-tuned ModernBERT model contains ~1.8GB of checkpoint files after training. To minimize bandwidth, disk usage, and container build times:

1. **Inference-Only Artifacts (~600MB)**:
   * `model.safetensors` (~571 MB)
   * `config.json` (~2.5 KB)
   * `tokenizer.json` (~3.5 MB)
   * `tokenizer_config.json` (~400 B)
2. **Excluded Artifacts**:
   * `optimizer.pt` (~1.2 GB) — Excluded from deployment as it is only needed for backpropagation during training.
3. **Docker Volume Mounting**:
   * Model weights are mounted into `/app/models` directly from the EC2 host.
   * Benefit: CI/CD rebuilds take only **10–15 seconds** because the 600MB model is not bundled into the Docker image layer on each commit.

---

## 5. Automated CI/CD Pipeline (GitHub Actions)

The deployment pipeline is fully automated using GitHub Actions (`.github/workflows/deploy.yml`).

### Workflow Architecture:
1. **Trigger**: Push or Pull Request to the `deployment` branch.
2. **Stage 1 (CI - Test Suite)**:
   * Sets up Python 3.11 runner.
   * Installs dependencies and PyTorch (CPU wheel).
   * Runs the complete **70 Unit & Integration Test Cases** via `pytest`.
   * **Quality Gate**: If any test fails, deployment stops immediately.
3. **Stage 2 (CD - AWS Deployment)**:
   * Securely authenticates with EC2 via SSH private key secret (`appleboy/ssh-action`).
   * Fetches latest commits from `origin/deployment`.
   * Executes `docker-compose up -d --build`.
   * Prunes unused intermediate images to maintain disk health.

### Required GitHub Secrets:

Configure these secrets under **Settings > Secrets and variables > Actions**:

| Secret Name | Description | Example / Value |
| :--- | :--- | :--- |
| `EC2_HOST` | Public IPv4 Address of EC2 | `16.171.197.26` |
| `EC2_USER` | Default Linux user for Ubuntu AMI | `ubuntu` |
| `EC2_SSH_KEY` | Private key (`.pem`) file content | `-----BEGIN RSA PRIVATE KEY----- ...` |

---

## 6. Server Management & Useful Commands

### Accessing the Server
```bash
ssh -i "nextgenqa-key.pem" ubuntu@<EC2_PUBLIC_IP>
```

### Viewing Live Container Logs
```bash
cd ~/NextGenQA/intelligent-user-story-generator-service
docker-compose logs -f app
```

### Checking Container Health Status
```bash
docker ps
```

### Restarting the Service Manually
```bash
docker-compose restart app
```

### Rebuilding Containers Manually
```bash
docker-compose up -d --build
```

---

## 7. Live Health Check & Documentation Endpoints

Once deployed, verify the service through the following endpoints:

* **Health Check**: `GET http://<EC2_PUBLIC_IP>:8001/health`
  ```json
  {
    "status": "ok",
    "service": "intelligent-user-story-generator",
    "environment": "production"
  }
  ```
* **Speech Module Health**: `GET http://<EC2_PUBLIC_IP>:8001/api/v1/speech/health`
* **Interactive Swagger UI**: `http://<EC2_PUBLIC_IP>:8001/docs`
* **ReDoc Documentation**: `http://<EC2_PUBLIC_IP>:8001/redoc`
