# Security Policy

## Supported Versions

Ground Station is a hobby project maintained in the author's spare time. Security fixes are
made against the latest release. Older releases are not supported; users should upgrade to
the latest available version before reporting a vulnerability.

| Version | Supported |
| --- | --- |
| Latest release | Yes |
| Older releases | No |

## Deployment and Threat Model

Ground Station is designed for amateur-radio and hobby ground stations operated on a trusted
private network. It is not designed as an internet-facing service or as a hardened multi-tenant
platform.

The security model assumes that:

* The host, container runtime, reverse proxy, and local network are administered by the owner.
* Administrator accounts are fully trusted. Administrators intentionally have broad control
  over hardware, services, integrations, database maintenance, and remote data-source URLs.
* Operator accounts and unauthenticated clients are not trusted with administrator privileges.
* The owner completes first-run setup before allowing untrusted clients onto the network. The
  first administrator is necessarily created without an existing authenticated account.
* TLS and internet access controls, when required, are provided by the deployment environment.

Exposing Ground Station directly to the public internet is outside the supported deployment
model. Reports are still welcome when they demonstrate a product security boundary can be
crossed under the assumptions above.

## In Scope

Examples of issues that are useful to report include:

* Authentication bypass after initial setup.
* Privilege escalation from an operator or unauthenticated client to administrator capabilities.
* Unauthorized control of station hardware or access to another user's protected data.
* Arbitrary file access, code execution, or escape beyond the application's intended data and
  process boundaries.
* Disclosure of credentials, session tokens, or integration secrets to an unauthorized party.
* Actions induced by an external attacker through a victim's authenticated browser session.
* A reproducible denial of service that does not depend on a trusted administrator deliberately
  starting a resource-intensive operation.

## Out of Scope and Accepted Risks

The following normally do not qualify as vulnerabilities for this project:

* A trusted administrator configuring a URL and causing Ground Station to request that URL.
* A trusted administrator importing, restoring, replacing, or deleting application data through
  an administrator-only maintenance feature.
* A trusted administrator controlling hardware, starting or stopping services, or changing
  system-wide settings as those features intend.
* Claiming a brand-new, network-exposed installation before its owner completes first-run setup.
  Keep a new installation on a trusted network until the first administrator has been created.
* Findings that require an attacker already to control the host, container runtime, reverse
  proxy, administrator account, or trusted LAN.
* Risks caused solely by deploying the application directly on the public internet, omitting TLS,
  using unsafe container privileges, or granting overly broad host filesystem permissions.
* Missing best-practice headers, version disclosure, self-XSS, or scanner-only findings without a
  demonstrated security impact.
* Dependency version reports without a reachable and relevant exploit in Ground Station.
* Theoretical issues without a reproducible path across one of the stated trust boundaries.

An issue is not automatically out of scope merely because an administrator uses the affected
feature. If an untrusted party can control the input or trigger the action, explain that attack
path in the report.

## Reporting a Vulnerability

Use GitHub's **Report a vulnerability** feature under the repository's **Security** tab. Do not
open a public issue for an undisclosed vulnerability.

Please include:

* The affected release or commit.
* The attacker's required access and role.
* The deployment assumptions needed for the attack.
* Reproduction steps or a minimal proof of concept.
* The security boundary crossed and the resulting practical impact.
* Any suggested fix, if available.

Test only against systems and data you own or have permission to use. Avoid service disruption,
privacy violations, persistence, and access beyond what is necessary to demonstrate the issue.

There is no bug-bounty program and no guaranteed response time. Reports that clearly fit the
supported threat model will be reviewed as maintainer availability permits.
