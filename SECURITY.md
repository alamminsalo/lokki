# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.3.x   | :white_check_mark: |
| < 0.3   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability within this project, please send an email to the maintainers. All security vulnerabilities will be promptly addressed.

Please include the following information:
- Description of the vulnerability
- Steps to reproduce the issue
- Potential impact of the vulnerability
- Any suggested fixes (optional)

## Security Best Practices

When using lokki in production:

1. **Credentials**: Ensure AWS credentials are properly secured and not committed to version control
2. **S3 Buckets**: Use appropriate bucket policies and access controls
3. **Environment Variables**: Never log or expose secret credentials
4. **Network**: Use private subnets for Lambda functions when possible
5. **Logging**: Be cautious about logging sensitive data in CloudWatch logs

## Dependencies

This project uses automated dependency scanning via pip-audit. Run it locally:

```bash
uv sync --extra dev
uv run pip-audit
```
