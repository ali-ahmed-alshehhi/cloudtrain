# 0013 — A small Pulumi layer above Terraform

- **Status:** proposed (contract change #147; accepted once agreed there)
- **Date:** 2026-11-22
- **Decided by:** Fatma and Hamda (Student 6), at the professor's request

## Context
The professor asked whether we can include Pulumi above Terraform. The course requires Terraform: the
seven mandatory demos are Terraform demos, and principle 7 says Terraform creates all cloud resources.
The feature freeze is Wed 25 Nov, so a replacement or conversion was out of the question.

## Decision
Terraform keeps creating every cloud resource. A small Pulumi program (`infrastructure/pulumi/`, Python)
sits above it:

1. It reads Terraform's outputs (`terraform output -json`) and creates **one** resource, the CloudWatch
   dashboard `<env>-cloudtrain`. Nothing in Terraform depends on it.
2. It never changes a Terraform resource, and Terraform never reads from Pulumi. The dependency only goes
   one way: Pulumi → Terraform outputs.
3. Pulumi's state is local (`pulumi login file://…`); no Pulumi Cloud account.
4. Order: `terraform apply`, then `pulumi up`. Tear down: `pulumi destroy`, then `terraform destroy`.
5. The seven mandatory Terraform demos stay the same. Pulumi is an optional 8th demo.

## Why
- It answers the professor's request without risking the mandatory Terraform work.
- The dashboard was the one monitoring piece still missing, and it fits the rule: something new that
  Terraform doesn't own and doesn't depend on.
- The professor agreed to this low-risk version.
- A spike on the AWS Emulator worked end to end (#147): `terraform apply`, `pulumi up`, `terraform plan`
  with no changes, then both destroys.

## Trade-offs
- Two tools and two state files; the destroy order matters (written in the README and the deployment guide).
- Each person sets a Pulumi passphrase (`PULUMI_CONFIG_PASSPHRASE`), even though the program has no secrets.
- Rejected: converting Terraform to Pulumi (`pulumi convert`), and running the Terraform modules inside
  Pulumi. Both would replace the Terraform the course requires.
