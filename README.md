# 🤖 Autonomous DevOps AI Agent

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Google Gemini](https://img.shields.io/badge/Google%20Gemini-2.0%20Flash-8E75B2?style=for-the-badge&logo=google-gemini&logoColor=white)](https://ai.google.dev/)
[![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-CI%2FCD-2088FF?style=for-the-badge&logo=githubactions&logoColor=white)](https://github.com/features/actions)

An event-driven, autonomous **DevOps AI Agent** built with Python and FastAPI that creates a self-healing CI/CD pipeline. The agent intercepts live `workflow_run` failure events from **GitHub Actions**, dynamically retrieves repository source context, diagnoses failure logs using **Google Gemini AI**, and automatically generates and opens structured **Pull Requests** with bug fixes on GitHub.

---

## 🏗️ System Architecture & Workflow Diagram

```text
 ┌────────────────┐       1. CI Build Fails        ┌───────────────────────┐
 │ GitHub Actions │ ──────────────────────────────► │ GitHub Webhook Event  │
 └────────────────┘                                └───────────┬───────────┘
                                                               │
                                         2. POST /webhook/github (HMAC Verified)
                                                               │
                                                               ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                       FastAPI DevOps Agent Backend                      │
 │                                                                         │
 │  ┌───────────────────────┐               ┌───────────────────────────┐  │
 │  │ 3. Fetch File Context │ ────────────► │ 4. Generate AI Code Fix   │  │
 │  │    (via PyGithub)     │               │    (Google Gemini API)    │  │
 │  └───────────────────────┘               └─────────────┬─────────────┘  │
 └────────────────────────────────────────────────────────┼────────────────┘
                                                          │
                                         5. Open Automated Pull Request
                                                          │
                                                          ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                        GitHub Repository Pull Request                   │
 │  • Branch: devops-agent-fix-a1b2c3d                                     │
 │  • Description: AI Explanation & Root Cause Analysis                    │
 └─────────────────────────────────────────────────────────────────────────┘