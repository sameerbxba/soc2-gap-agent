<!-- SYNTHETIC DOCUMENT. Northwind Cloud Systems Inc. does not exist. -->
<!-- Written as test data for the SOC 2 control-gap agent. Not a real audit report. -->

<!-- page: 1 -->
# Northwind Cloud Systems Inc.

## SOC 2 Type 2 Report
### Report on Controls Relevant to Security and Confidentiality

**Period covered:** 1 October 2025 through 30 June 2026

**Service auditor:** Baywood Assurance LLP, Chartered Professional Accountants

**Report date:** 14 August 2026

---

<!-- page: 3 -->
## Section I — Management's Assertion

We, the management of Northwind Cloud Systems Inc. ("Northwind"), are responsible
for the design, implementation and operation of controls within the Northwind
Workflow Platform system throughout the period 1 October 2025 to 30 June 2026.

We assert that, throughout the period stated above:

a. the description of the system presents the Northwind Workflow Platform as
   designed and implemented;
b. the controls stated in the description were suitably designed to provide
   reasonable assurance that the applicable trust services criteria for
   **Security and Confidentiality** would be met; and
c. the controls stated in the description operated effectively throughout the
   period, subject to the deviations described in Section IV.

The description indicates that certain applicable trust services criteria can be
met only if complementary user entity controls assumed in the design of our
controls are suitably designed and operating effectively. The description does
not extend to controls of the user entities.

The description also excludes the controls of Amazon Web Services, Inc., which
Northwind uses as a subservice organization for infrastructure hosting. The
carve-out method has been used in this report.

Signed,
R. Vance, Chief Technology Officer, Northwind Cloud Systems Inc.

---

<!-- page: 5 -->
## Section II — Independent Service Auditor's Report

To the management of Northwind Cloud Systems Inc.

### Scope

We have examined Northwind's description of the Northwind Workflow Platform
system throughout the period 1 October 2025 to 30 June 2026, and the suitability
of the design and operating effectiveness of controls stated in the description
to meet the criteria for the **Security and Confidentiality** categories set
forth in TSP section 100, 2017 Trust Services Criteria.

Northwind uses Amazon Web Services, Inc. as a subservice organization for
infrastructure hosting. **The description presents Northwind's controls and
excludes the controls of the subservice organization.** Our examination did not
extend to the controls of the subservice organization.

The description indicates that certain applicable trust services criteria can be
met only if complementary user entity controls assumed in the design of
Northwind's controls are suitably designed and operating effectively. Our
examination did not extend to such complementary user entity controls.

### Opinion

In our opinion, in all material respects, based on the criteria described in
management's assertion:

a. the description presents the system that was designed and implemented
   throughout the period;
b. the controls stated in the description were suitably designed throughout the
   period; and
c. the controls stated in the description operated effectively throughout the
   period.

The deviations identified in our testing are described in Section IV. In our
judgment these deviations, individually and in aggregate, do not result in the
applicable trust services criteria not being met.

Baywood Assurance LLP
Toronto, Ontario
14 August 2026

---

<!-- page: 9 -->
## Section III — Description of the System

### 3.1 Company overview

Northwind Cloud Systems Inc. provides a multi-tenant workflow automation
platform used by customers to route approvals, store supporting documentation
and generate operational reporting. The platform is delivered as software as a
service and accessed through a web application and a public API.

<!-- page: 10 -->
### 3.2 Infrastructure and subservice organizations

The Northwind Workflow Platform is hosted entirely on Amazon Web Services in the
ca-central-1 and us-east-1 regions. Northwind relies on AWS for physical and
environmental security, hardware maintenance, network infrastructure and the
managed database service.

**Controls operated by Amazon Web Services are excluded from the scope of this
report.** User entities relying on this report should obtain and evaluate the
most recent SOC 2 report issued in respect of Amazon Web Services and consider
whether the controls described therein, together with the controls described in
this report, are sufficient for their purposes.

<!-- page: 11 -->
### 3.3 Trust services criteria in scope

This examination covers the **Security** and **Confidentiality** trust services
categories.

The **Availability**, **Processing Integrity** and **Privacy** categories are
**not** in scope for this examination. Controls relating to system uptime,
capacity management, backup restoration testing, disaster recovery and
processing accuracy were not examined and no opinion is expressed on them.

<!-- page: 13 -->
### 3.4 Complementary user entity controls

The design of Northwind's controls assumes that user entities have implemented
the following controls. Northwind's controls alone are not sufficient to meet
the applicable trust services criteria without them.

**CUEC-1.** User entities are responsible for provisioning, reviewing and
deprovisioning their own users within the Northwind administrative console,
including removal of access upon termination of their own personnel.

**CUEC-2.** User entities are responsible for configuring and enforcing
multi-factor authentication for their own user population. Northwind provides
the capability; enforcement is a tenant-level setting controlled by the user
entity.

**CUEC-3.** User entities are responsible for classifying the data they upload
to the platform and for not uploading data types the platform is not designed to
hold, including payment card data and government identifiers.

**CUEC-4.** User entities are responsible for reviewing Northwind's published
notification of material changes to the platform and assessing the impact of
those changes on their own control environment.

**CUEC-5.** User entities are responsible for monitoring their own tenant audit
logs, which Northwind makes available through the API for a rolling 90 day
period.

<!-- page: 16 -->
### 3.5 Change management

Changes to production are managed through a documented change control process.
All code changes require a pull request, a peer review by an engineer other than
the author, and an automated test suite pass before merge. Deployment to
production is performed through an automated pipeline. **The engineer who
authors a change cannot approve or deploy that change.** Emergency changes
follow an expedited path and are reviewed retrospectively within five business
days.

<!-- page: 18 -->
### 3.6 Logical access

Access to production systems is granted on the principle of least privilege and
requires documented approval from the system owner. Multi-factor authentication
is enforced for all administrative and remote access to production systems.
Access rights are reviewed on a quarterly basis by the system owner.

Northwind's internal policy requires that access for departing personnel be
revoked **within one business day of the termination effective date**.

<!-- page: 20 -->
### 3.7 Encryption and data protection

Customer data is encrypted in transit using TLS 1.2 or higher. Customer data is
encrypted at rest using **AES-256** through the managed encryption facilities of
the subservice organization. Encryption keys are managed through the subservice
organization's key management service and rotated annually.

<!-- page: 21 -->
### 3.8 Security testing

Northwind performs an annual penetration test of the production environment.
**The penetration test is performed by Northwind's internal security engineering
team.** Findings are tracked to remediation in the engineering backlog and rated
using CVSS. Northwind does not currently engage an independent third party to
perform penetration testing.

<!-- page: 22 -->
### 3.9 Incident response and notification

Northwind maintains a documented incident response plan that is tested annually
through a tabletop exercise. In the event of a confirmed security incident
affecting customer data, Northwind will notify affected user entities
**without undue delay**. Notification timing commitments specific to individual
user entities, where they exist, are set out in the applicable customer
agreement and are not addressed in this report.

<!-- page: 23 -->
### 3.10 Backup

Customer data is backed up continuously to the subservice organization's managed
backup service with a retention period of 35 days. Restoration procedures are
documented. **Testing of backup restoration falls within the Availability
category, which is not in scope for this examination.**

---

<!-- page: 24 -->
## Section IV — Trust Services Criteria, Controls and Tests of Controls

The following table describes the controls, the tests performed by the service
auditor, and the results of those tests.

<!-- page: 25 -->
### CC6.1 — Logical access security

**Control:** Multi-factor authentication is enforced for all administrative and
remote access to the production environment.

**Test performed:** Inspected the identity provider configuration for the
production environment. For a sample of 25 administrative accounts, inspected
authentication logs to determine whether multi-factor authentication was
enforced at each authentication event during the period.

**Result:** No exceptions noted.

<!-- page: 26 -->
### CC6.2 — Access provisioning and removal

**Control:** Access for terminated personnel is revoked within one business day
of the termination effective date.

**Test performed:** For a population of 25 personnel terminated during the
period, inspected the termination record and the corresponding access revocation
record to determine whether access was revoked within one business day.

**Result:** **Exception noted. For 2 of the 25 terminations tested, access to
the production environment was not revoked until 4 and 9 business days
respectively after the termination effective date.** In both instances there was
no evidence of access being used after the termination effective date.
Management's response is included in Section V.

<!-- page: 28 -->
### CC6.7 — Encryption in transit

**Control:** Customer data transmitted over public networks is encrypted using
TLS 1.2 or higher.

**Test performed:** Inspected the TLS configuration of all public endpoints and
attempted connections using deprecated protocol versions.

**Result:** No exceptions noted.

<!-- page: 29 -->
### CC7.2 — System monitoring

**Control:** Security events from production systems are forwarded to a central
log platform and alerting rules are configured for defined event types.

**Test performed:** Inspected the log forwarding configuration and the alerting
rule set. For a sample of 15 alerts raised during the period, inspected the
ticket record to determine whether the alert was triaged.

**Result:** No exceptions noted.

<!-- page: 31 -->
### CC8.1 — Change management

**Control:** Changes to production require peer review by an individual other
than the author, and the author cannot deploy their own change.

**Test performed:** For a sample of 40 production changes released during the
period, inspected the pull request record to determine that the reviewer and the
deploying user were each different from the change author.

**Result:** No exceptions noted.

<!-- page: 33 -->
### CC9.2 — Vendor and subservice management

**Control:** Northwind obtains and reviews the SOC 2 report of its subservice
organization annually and documents the review.

**Test performed:** Inspected the most recent subservice organization report
obtained by Northwind and the documented review.

**Result:** No exceptions noted.

<!-- page: 35 -->
### C1.1 — Confidential information identification

**Control:** Customer data is classified on ingestion according to the tenant
configuration and access is restricted to the owning tenant.

**Test performed:** For a sample of 10 tenants, attempted cross-tenant data
access using authenticated sessions from other tenants.

**Result:** No exceptions noted.

---

<!-- page: 41 -->
## Section V — Other Information Provided by Management

This section is presented by management of Northwind Cloud Systems Inc. and is
not covered by the service auditor's opinion.

### Management's response to the deviation noted at CC6.2

The two instances of delayed access revocation arose from terminations processed
during a period in which the human resources system integration to the identity
provider was being migrated. Manual notification to the security team was
required during the migration window and was not completed within the policy
timeframe in these two cases.

The integration was completed on 12 May 2026 and termination events now trigger
automated deprovisioning. Management considers the underlying cause remediated.
No independent testing of the remediated control has been performed by the
service auditor, as the remediation was completed shortly before the end of the
examination period.

### Note on encryption at rest

Encryption at rest is implemented through the managed encryption facilities of
the subservice organization and is therefore dependent on controls operated by
that organization. It was not separately tested by the service auditor in this
examination.
