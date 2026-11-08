# Security policy

BrainOS is research software, not a medical device. What it protects, and what it does not,
is described in [docs/SECURITY.md](docs/SECURITY.md). In short:

- it listens only on this computer (127.0.0.1) and has no user accounts, so anyone who can
  run programs on the computer can use it;
- it refuses requests from other web sites and from other host names;
- its data folder is readable only by your user account; recordings are not encrypted;
- it never sends commands to a device.

## Supported versions

Security fixes go into the latest release only.

## Reporting a vulnerability

Please do **not** open a public issue for a security problem. Use GitHub's private reporting:
the repository's **Security** tab → **Report a vulnerability**. Include what you found, how to
reproduce it, and the version (`brainos version`, or the support report from
**Advanced → Support report**, which contains no neural or personal data).

Never include neural recordings, participant information or credentials in a report.

You will get an acknowledgement as soon as the maintainers have seen the report, and the fix
will be announced in the release notes once it is available.
