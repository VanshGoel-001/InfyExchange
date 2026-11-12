# DevSecOps Pipeline

## Automated Controls

| Control | Pipeline implementation | Release gate |
| --- | --- | --- |
| Build and test | Frontend build; backend pytest; Docker build configuration | Required before deploy |
| SAST | Bandit and CodeQL for Python and JavaScript/TypeScript | High-confidence findings block or alert through code scanning |
| Dependency security | `npm audit`, `pip-audit`, and PR dependency review | High/critical dependency review findings block PRs |
| Secret detection | Gitleaks scans repository history and changes | Any detected secret fails CI |
| IaC/workflow checks | Trivy misconfiguration scan and actionlint | High/critical findings or invalid workflows fail CI |
| Container security | Trivy scans the release image for fixable high/critical OS and library vulnerabilities | Blocks deployment |
| Software inventory | BuildKit SBOM/provenance metadata and retained CycloneDX SBOM | SBOM generated for the release image |
| Artifact integrity | Build once, then scan and deploy the Artifact Registry image by digest | Prevents deployment of a separately rebuilt image |
| Deployment identity | GitHub OIDC through Workload Identity Federation | No long-lived cloud key in GitHub |
| Secret delivery | Cloud Run reads database and application secrets from Secret Manager | Secrets are not built into the image or frontend |
| Deployment order | CI gates, Cloud Run health check, then Cloudflare Pages | Pages does not deploy if the API stage fails |

Actions are pinned to immutable commit SHAs. Dependabot checks pinned actions, Docker base images, npm packages, and Python packages weekly.

## Required Repository and Cloud Settings

These controls cannot be enforced by workflow YAML alone. Configure them in GitHub and Google Cloud before treating the pipeline as production-ready:

- Protect `main` and `deploy/neon-cloudrun-cloudflare-pages`: require pull requests, at least one review, dismiss stale approvals, require the relevant CI/CodeQL/dependency-review checks, and block force-pushes and branch deletion.
- Configure the `neon-staging` environment with required reviewers and restrict deployment to the Neon deployment branch.
- Restrict the Workload Identity Federation provider to this repository and deployment branch. Give the deploy identity only Artifact Registry Writer, Cloud Run deployment, and service-account impersonation permissions.
- Give the Cloud Run runtime identity Secret Manager access only to the six application secrets. Do not grant the GitHub deploy identity access to secret payloads.
- Enable GitHub secret scanning and push protection, Dependabot alerts, and code scanning for the repository. Review and triage CodeQL findings.
- Create the Artifact Registry Docker repository and a staging Cloud Run service before the first deployment. Use a staging database and non-production Cloudinary account for validation.
- Configure Cloud Run logs/alerts, Neon backup/PITR retention, and periodic restore exercises.

## Residual Verification

The workflow does not claim complete compliance with a particular regulatory standard. GitHub environment approvals, branch protection, cloud IAM conditions, and alerting are external settings and must be verified by an administrator. Dynamic API scanning with ZAP remains a staging operational check using `scripts/security/zap-api-scan.ps1`; do not run active or destructive scans against production.