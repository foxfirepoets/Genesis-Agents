# Genesis Agents — White-Label Marketplace Edition

This repository contains the white-label Genesis Agents marketplace: **24 specialized AI agents** built on the Genesis autonomous runtime, ready for deployment and customization.

## Marketplace Agent Catalog

The following 24 agents are the canonical white-label set, each with dedicated skill bundles in `skill_bundles/`:

### Core Operations
- **genesis-ai-vision** — Computer vision, image analysis, OCR, and visual content processing
- **genesis-analyst** — Business intelligence, data analysis, and reporting
- **genesis-workflow-automator** — Multi-step workflow orchestration and task automation

### Development & Deployment
- **genesis-builder** — Code generation, implementation, and software engineering
- **genesis-deploy** — Deployment automation, CI/CD, and infrastructure orchestration
- **genesis-qa** — Quality assurance, testing, and validation
- **genesis-research** — Technical research, investigation, and documentation

### Business Functions
- **genesis-billing** — Billing operations, invoice management, and revenue tracking
- **genesis-commerce** — E-commerce operations, product management, and order processing
- **genesis-finance** — Financial operations, reporting, and accounting
- **genesis-hr** — Human resources, recruitment, and employee management
- **genesis-legal** — Contract review, compliance, and legal documentation
- **genesis-pricing** — Pricing strategy, analysis, and optimization

### Customer-Facing
- **genesis-content** — Content creation, editing, and management
- **genesis-email** — Email automation, composition, and campaign management
- **genesis-marketing** — Marketing campaigns, analytics, and strategy
- **genesis-onboarding** — User onboarding, training, and documentation
- **genesis-support** — Customer support, issue resolution, and ticket management

### Technical Operations
- **genesis-data-pipeline** — Data integration, ETL, and pipeline management
- **genesis-domain** — Domain management, DNS, and web infrastructure
- **genesis-maintenance** — System maintenance, monitoring, and health checks
- **genesis-meta** — Meta-orchestration, agent coordination, and delegation
- **genesis-security** — Security audits, vulnerability scanning, and compliance
- **genesis-seo** — SEO optimization, analytics, and content strategy

## Deployment

**Production:** `https://swarmsync-agents.onrender.com`  
**Endpoint:** `POST /agents/{slug}/run`

See `CLAUDE.md` for technical details and `RUNTIME_RUNBOOK.md` for operations.

## Legacy & Custom Deployments

Enterprise-specific skill bundles and custom deployment configurations have been archived to maintain the clean white-label set. Contact SwarmSync for custom agent development or enterprise-specific extensions.

---

**Version:** 2.0 White-Label  
**Last Updated:** September 2026
