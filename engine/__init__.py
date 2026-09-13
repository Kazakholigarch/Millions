"""Revenue engine: find businesses with provable, expensive defects — and prove it.

The strategy this implements is in STRATEGY.md. The short version: closing
$100k of contracted work in 30 days needs ~1,700 outbound touches, and touches
only convert when they carry a *real measurement* of a *real defect* on the
prospect's own site. Hand-personalising that many is impossible; fabricating the
evidence is fatal. So the evidence gets measured, by this package.

Every claim this package emits traces back to something it actually observed
over the wire. See `outreach.verify_grounded` for the enforcement.
"""

__version__ = "1.0.0"
