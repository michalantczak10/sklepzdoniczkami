AWS IAM user for backups — recommended steps

1. Create IAM policy using docs/aws-backup-iam-policy.json: replace YOUR_BACKUP_BUCKET, REGION, ACCOUNT_ID, YOUR_KMS_KEY_ID as needed.
2. Create an IAM user (e.g., actions-backup-user) and attach the policy. Grant programmatic access and save AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.
3. Restrict the IAM user to the specific bucket and KMS key. Do NOT grant wide admin permissions.
4. In GitHub repository settings → Secrets, configure:
   - AWS_ACCESS_KEY_ID
   - AWS_SECRET_ACCESS_KEY
   - BACKUP_S3_BUCKET
   - AWS_REGION (optional)
   - AWS_KMS_KEY_ID (optional)
5. Test: run the db-backup workflow (workflow_dispatch) and confirm object appears in S3 and has SSE-KMS if configured.

Security notes:
- Rotate keys periodically.
- Use least-privilege IAM principals.
- Consider using AWS IAM roles and OIDC for GitHub Actions for better security (recommended long-term).

Using GitHub Actions OIDC (recommended)

1. Create an IAM role for OIDC:
   - In AWS IAM, Create role → Web identity → Select provider: "GitHub" (you may need to create an identity provider for https://token.actions.githubusercontent.com).
   - Trust policy should restrict to your repository and optionally branch or environment. Example condition (replace owner/repo):
     "StringLike": {"token.actions.githubusercontent.com:sub": "repo:michalantczak10/sklepzdoniczkami:*"}
2. Attach a policy to the role that grants the minimal S3 and KMS actions (use docs/aws-backup-iam-policy.json as a starting point).
3. Note the Role ARN (arn:aws:iam::ACCOUNT_ID:role/GitHubActionsBackupRole).
4. In your GitHub Actions workflow, request OIDC token and assume the role using aws-cli v2 or aws-actions/configure-aws-credentials with oidc: true.

Example workflow snippet (use in .github/workflows/db-backup.yml when uploading to S3):

- name: Configure AWS credentials via OIDC (recommended)
  uses: aws-actions/configure-aws-credentials@v3
  with:
    role-to-assume: arn:aws:iam::ACCOUNT_ID:role/GitHubActionsBackupRole
    aws-region: us-east-1
    role-session-name: github-actions-backup
    oidc: true

This avoids committing or storing long-lived AWS keys in repository secrets. Test the role by triggering the workflow and verifying S3 upload and KMS encryption as before.