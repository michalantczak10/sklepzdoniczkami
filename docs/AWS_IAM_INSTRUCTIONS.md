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