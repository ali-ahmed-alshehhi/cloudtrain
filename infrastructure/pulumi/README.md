# Pulumi layer: the CloudWatch dashboard

Owners: Hamda + Fatma. Decision [0013](../../docs/decisions/0013-pulumi-layer-above-terraform.md).

**Terraform creates every cloud resource.** This small Pulumi program sits above it: it reads
Terraform's outputs and creates **one** resource, the CloudWatch dashboard `<env>-cloudtrain`. It never
changes a Terraform resource, and Terraform never reads from it.

| Widget | Metric | From Terraform output |
|---|---|---|
| Messages waiting | `AWS/SQS` `ApproximateNumberOfMessagesVisible` | the three queue URLs |
| Oldest message | `AWS/SQS` `ApproximateAgeOfOldestMessage` | `training_jobs_queue_url`, `job_events_queue_url` |
| GPU workers running | `AWS/AutoScaling` `GroupInServiceInstances` | both pools' Auto Scaling groups |
| Load balancer: requests and 5xx | `AWS/ApplicationELB` | `alb_arn_suffix` |
| ECS CPU and memory | `AWS/ECS` | `ecs_cluster_name` |

On the AWS Emulator (decision 0011) the dashboard is created but gets no live data; the live view is the
local Grafana (#109).

## Run it (AWS Emulator)
Once: install the CLI (`brew install pulumi/tap/pulumi`), then from this folder:

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
mkdir -p state && pulumi login "file://$PWD/state"     # local state, no Pulumi Cloud account
export PULUMI_CONFIG_PASSPHRASE='<your own passphrase>'  # needed even with no secrets; never commit it
pulumi stack select dev --create
pulumi config set useEmulator true
```

Every time, with the emulator running (`../scripts/emulator-up.sh`: its credentials only exist while it runs) and **after** `terraform apply` in `infrastructure/`:

```bash
source ../scripts/emulator-env.sh
terraform -chdir=.. output -json > tf-outputs.json
pulumi preview          # expect: + 3 to create (stack, AWS provider, dashboard)
pulumi up --yes
pulumi stack output     # dashboard_name = dev-cloudtrain, widget_count = 5
```

**Tear down in this order:** `pulumi destroy --yes` **first**, then `terraform destroy` in `infrastructure/`.
The dashboard points at Terraform's resources, so it goes before them.

On real AWS: skip `useEmulator` (it defaults to false) and use the real `terraform output -json`.

## Settings (`pulumi config set <key> <value>`)
| Key | Default | Meaning |
|---|---|---|
| `useEmulator` | `false` | send AWS calls to the emulator |
| `emulatorEndpoint` | `https://127.0.0.1:9297` | the emulator's address |
| `terraformOutputsFile` | `tf-outputs.json` | where `terraform output -json` was saved (or `TF_OUTPUTS_FILE`) |
| `environment` | `dev` | name prefix and `Environment` tag |
| `region` | `us-east-1` | AWS region |
