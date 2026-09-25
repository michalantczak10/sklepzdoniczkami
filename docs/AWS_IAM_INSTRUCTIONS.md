ARCHIVAL NOTICE: AWS instructions (archived)

This file previously contained instructions for configuring AWS S3/KMS and IAM roles for storing backups. The project currently uses GitHub Actions artifacts only and does not require AWS configuration.

If you later decide to re-enable AWS uploads, see the commit history for the removed steps or restore this file from Git history. For safety, AWS-related credentials and long-lived keys should NOT be stored in chat.

(If needed in future: create an IAM role for OIDC or a least-privilege IAM user, attach S3 + KMS permissions per docs/aws-backup-iam-policy.json.)

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