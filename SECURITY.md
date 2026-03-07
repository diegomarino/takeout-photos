# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.x.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take the security of `takeout-photos` seriously. If you believe you have found a security vulnerability, please report it to us as described below.

### Where to Report

**Please do NOT report security vulnerabilities through public GitHub issues.**

Instead, please use GitHub's private vulnerability reporting feature:

1. Go to the [Security tab](https://github.com/diegomarino/takeout-photos/security)
2. Click "Report a vulnerability"
3. Fill out the vulnerability report form

### What to Include

Please include the following information in your report:

- Type of vulnerability (e.g., buffer overflow, SQL injection, cross-site scripting, etc.)
- Full paths of source file(s) related to the manifestation of the vulnerability
- The location of the affected source code (tag/branch/commit or direct URL)
- Any special configuration required to reproduce the issue
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue, including how an attacker might exploit it

### What to Expect

After submitting a vulnerability report, you can expect:

1. **Acknowledgment**: We will acknowledge receipt of your vulnerability report within 48 hours.

2. **Assessment**: We will investigate and assess the vulnerability, typically within 5 business days.

3. **Updates**: We will keep you informed about our progress fixing the vulnerability.

4. **Disclosure**: Once the vulnerability is fixed, we will:
   - Release a security update
   - Publish a security advisory
   - Credit you for the discovery (unless you prefer to remain anonymous)

### Preferred Languages

We prefer all communications to be in English.

## Security Best Practices

When using `takeout-photos`, we recommend:

1. **Keep Updated**: Always use the latest version to benefit from security patches.

2. **Verify Downloads**: When installing from PyPI, verify the package integrity:
   ```bash
   pip install takeout-photos --require-hashes
   ```

3. **Validate Input**: Be cautious when processing Takeout archives from untrusted sources.

4. **File Permissions**: Ensure output directories have appropriate permissions:
   - Input archives: read-only
   - Output directory: write access only for your user
   - Database file: read-write access only for your user

5. **Exiftool Safety**: Keep ExifTool updated to the latest version for security patches.

6. **Sandboxing**: Consider running `takeout-photos` in a sandboxed environment or container when processing untrusted archives.

## Security Update Policy

- **Critical vulnerabilities**: Patched and released within 48 hours
- **High-severity vulnerabilities**: Patched and released within 7 days
- **Medium/Low-severity vulnerabilities**: Patched in the next regular release

Security updates will be clearly marked in the changelog and release notes.

## Known Security Considerations

### Exiftool Dependency

This tool relies on ExifTool for metadata processing. Ensure you:
- Use ExifTool version 12.76 or later
- Keep ExifTool updated regularly
- Review ExifTool's own security advisories

### File System Operations

`takeout-photos` performs extensive file system operations:
- Creating and extracting ZIP archives
- Reading and writing metadata
- Copying and moving files

Ensure you:
- Run the tool with minimal necessary privileges
- Validate the source archive integrity before processing
- Have adequate disk space and backups

### Database Security

The SQLite database stores processing state:
- Keep the database file permissions restricted
- Do not share the database across untrusted systems
- The database may contain file paths and metadata from your archives

## Acknowledgments

We thank the security researchers and users who responsibly disclose vulnerabilities to help keep `takeout-photos` secure.

---

**Last Updated**: 2026-01-27
