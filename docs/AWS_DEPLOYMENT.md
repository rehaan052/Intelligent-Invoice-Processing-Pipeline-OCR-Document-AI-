# Deploying to AWS (ECR + ECS Fargate)

These steps are written but **not executed** by the project author's tooling, because deployment needs
your AWS account. Replace `<ACCOUNT_ID>` and the region as needed. Use an IAM user or role with the
**minimum** permissions below, not `AdministratorAccess`.

## 1. Create the ECR repository

```bash
aws ecr create-repository --repository-name invoice-ocr --region ap-south-1
```

## 2. Build and push the image

```bash
aws ecr get-login-password --region ap-south-1 | \
  docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.ap-south-1.amazonaws.com

docker build -t invoice-ocr .
docker tag invoice-ocr:latest <ACCOUNT_ID>.dkr.ecr.ap-south-1.amazonaws.com/invoice-ocr:latest
docker push <ACCOUNT_ID>.dkr.ecr.ap-south-1.amazonaws.com/invoice-ocr:latest
```

## 3. Run on ECS Fargate

1. Create a cluster: ECS console -> Clusters -> Create (Fargate).
2. Task definition: Fargate, **0.5 vCPU / 1 GB** is enough, container port `8000`, image from step 2.
3. Container health check: `CMD-SHELL, python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"`.
4. Logging: `awslogs` driver, so the app's request logs land in CloudWatch.
5. Service: 1+ tasks behind an Application Load Balancer, target group health check path `/health`.
6. Security group: allow inbound `80/443` to the ALB only. Tasks accept traffic from the ALB only.

## 4. Auto-scaling and cost

- Scale on CPU (target about 60%), since OCR is CPU-bound. Keep `--workers 1` per container and scale out with more tasks.
- Fargate Spot works for batch workloads. Set a minimum of 1 on-demand task for the API.
- Cost levers: lower `MAX_IMAGE_SIDE`, scale to zero out of hours, and set a CloudWatch budget alarm.

## 5. CI/CD from GitHub Actions

The `push-ecr` job in `.github/workflows/ci.yml` is disabled by default. To enable it:

1. Repository -> Settings -> Secrets and variables -> Actions -> **Secrets**:
   `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`, `ECR_REPO` (for example `invoice-ocr`).
2. Same page -> **Variables**: add `ENABLE_ECR_PUSH` = `true`.
3. To redeploy automatically, add a step after the push: `aws ecs update-service --cluster <c> --service <s> --force-new-deployment`.

Better still, use GitHub OIDC with an IAM role instead of long-lived keys.

## 6. Minimum IAM permissions for the CI user

`ecr:GetAuthorizationToken`, `ecr:BatchCheckLayerAvailability`, `ecr:InitiateLayerUpload`,
`ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`, `ecr:PutImage`, and (for redeploys) `ecs:UpdateService`.

## 7. Security notes for real invoices

Invoices contain PII and financial data.

- Do not log `raw_text` in production (the API returns it on demand but never logs it).
- Encrypt S3 buckets (SSE-KMS) if you store uploads, and set a lifecycle rule to delete them.
- Keep the service in private subnets behind the ALB, and add authentication (API key or Cognito).

## 8. Possible extensions

- **S3 + SQS + Lambda or ECS worker** for asynchronous batch processing.
- **CloudWatch metrics** from the `/metrics` counters (latency, failure rate, low-confidence rate).
- **SageMaker** or a GPU service if you later swap in a heavier OCR or VLM model.
