"""erdos_engine: computational attacks on open Erdős problems.

The engine never claims to *solve* a problem unless a finite certificate
settles it.  Typical outputs are (a) counterexamples, which settle a
falsifiable problem, (b) examples, which settle a verifiable problem, or
(c) exhaustive verifications up to a bound, which settle nothing but extend
the known frontier.  Every result carries a certificate that an independent
checker (separate code path) re-validates before anything is published.
"""

__version__ = "0.1.0"
