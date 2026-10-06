# erdos-engine

Software for computational attacks on open [Erdős problems](https://www.erdosproblems.com),
built so that a result can be trusted, checked against prior work, and taken through the
publication process.

## What it does, and what it does not

No program can be expected to solve open Erdős problems, and this one does not claim to.
What it can do:

- **Settle a problem by a finite certificate**: a counterexample for a *falsifiable* problem,
  or an example for a *verifiable* one, if one exists in the searched range.
- **Push a verification frontier**: prove a statement for every case up to a bound. This
  settles nothing, but it is the most common kind of computational contribution.
- **Compute associated sequences**, e.g. to link a problem to the OEIS.

Each result carries a machine-readable **certificate**. A second implementation that shares
no code with the search **re-validates** it. A **novelty gate** compares the result against
what has already been reported on the problem's forum thread. Only after that does the
software assemble a **publication packet**: paper, arXiv tarball, forum-comment draft, data
deposit metadata and checklist. It never submits anything itself.

## Headline result: Erdős Problem #458

Problem #458 (Erdős–Graham) asks whether `lcm(1..p_{k+1}-1) < p_k · lcm(1..p_k)` for every `k`.
Its status is *falsifiable*.

The forum frontier before this work was `10^20`. That result relies on the distributed
prime-gap search above `4·10^18`, which has not been refereed. This engine proves the
statement for all `p_{k+1} ≤ 10^21` **without using any prime-gap table**:

- **(A)** Every prime power `q^a ≤ X` with `a ≥ 3` is located inside its exact prime gap,
  and the product criterion is checked for that gap.
- **(B)** Between every pair of consecutive prime squares a prime is exhibited, so no gap
  contains two prime squares. Each witness carries a Pocklington certificate, with
  deterministic Miller–Rabin below ψ₁₃ as the fallback.
- **(C)** The remaining gaps follow trivially.

Run figures:

- (A) 683,532 prime powers with `a ≥ 3`, in 683,531 distinct gaps. Exactly one gap, `(2179, 2203)`,
  holds two of them. The worst ratio is still the gap `(7, 11)` with product 6.
- (B) 1,367,199,811 witnesses, one for each prime `q ≤ 31,622,776,601`. 99.72% are
  Pocklington-certified and the rest use deterministic Miller–Rabin. The scan took 6.2
  CPU-hours on 3 cores.
- The independent checker recomputed (A) in full and reproduced 25 random chunks of (B) bit for bit.
  The witness count equals π(31,622,776,601) = 1,367,199,811, computed by a sieve-free
  prime-counting algorithm.
- Cross-check against an independent forum computation: the engine finds exactly the 341,805
  prime powers with `a ≥ 3` below `1.05·10^20` reported there.

The run, certificate and check report are in `results/p458/X1e21/`. The generated paper,
forum draft and publication checklist are in `results/p458/X1e21/packet/`.

## Solvers

| # | status | what the solver does | independent check |
|---|---|---|---|
| 458 | falsifiable | certificate (A)+(B)+(C) above; C kernel, chunked, resumable | pure-Python re-derivation of (A); sampled chunks of (B) reproduced bit-for-bit via witness digests; literal lcm check on a prefix |
| 647 | verifiable | prefix-max search for `max_{m<n}(m+τ(m)) ≤ n+2` | second τ algorithm (spf sieve); explicit refuting `m` for sampled `n` |
| 699 | falsifiable | Kummer-carry bitmasks over all `i<j≤n/2` | exact big-integer gcds |
| 848 | decidable | exact max clique for `ab+1` never squarefree; compares with `7 (mod 25)` | witness sets by trial division; Bron–Kerbosch re-derivation |
| 993 | falsifiable | all free trees (counts checked against A000055), independence polynomials | deletion recurrence, brute force, Prüfer enumeration |
| 375 | falsifiable | Grimm's conjecture via smooth-element matching | full bipartite matching without the shortcut |

Solvers other than #458 run at replication scale. The forum frontiers are far ahead of
them, for example `10^22` for #647 and 32-vertex trees for #993. The novelty gate labels
their results as replications.

## Install and use

```bash
pip install -e '.[fast,test]'        # needs a C compiler for the fast kernel (falls back to Python)

erdos-engine sync                    # refresh the community database (teorth/erdosproblems)
erdos-engine triage                  # open problems ranked by amenability
erdos-engine dossier 458             # statement, forum comments, largest claimed frontier, AI disclosures
erdos-engine run 458 X=1e15          # search + independent check -> results/p458/<run-id>/
erdos-engine check results/p458/<run-id> --thorough
erdos-engine publish results/p458/<run-id> --author "Your Name"
erdos-engine demo                    # quick run + check of every solver
```

`erdos-engine run 458 X=10**21 workers=4 checkpoint=path.jsonl` resumes from the checkpoint
if it is interrupted.

## Trust model

1. **Primality.** The engine only ever states that a number is prime on the strength of a
   proof. That proof is either Miller–Rabin with the first 13 prime bases, which is
   deterministic for `n < ψ₁₃ ≈ 3.3·10^24` (Sorenson–Webster), or a Pocklington–Lehmer
   certificate. Beyond ψ₁₃ the code refuses to answer instead of answering
   probabilistically. A test demonstrates that ψ₁₃ itself passes all 13 bases.
2. **Independent re-validation.** Every solver's `check` uses a different algorithm and a
   different implementation. Witness rules are pure functions of the input, so a digest
   over the whole witness sequence lets a slow Python re-implementation confirm that the
   C kernel produced identical witnesses.
3. **Integrity.** Run directories carry SHA-256 manifests. Publication refuses a tampered
   run, a failed or missing check, or an inconclusive outcome.
4. **Adversarial tests.** The tests tamper with certificates (digests, counts, missing
   chunks, inflated bounds, fake witnesses) and inject bugs (a subtly wrong primality test,
   a wrong witness rule). Each one must be detected.

## Publication workflow

`erdos-engine publish` writes a packet containing:

- `paper/main.tex`, `main.pdf`, `arxiv-submission.tar.gz` (amsart, with `.bbl` included).
  The prior-work paragraph is assembled from the forum thread and marked `TODO(human)`.
- `forum_comment.md`: a draft for the problem's erdosproblems.com thread, with the AI-use
  disclosure that community expects.
- `database_update.md`: whether `teorth/erdosproblems` should change. Search bounds do
  *not* go there, per its CONTRIBUTING guide.
- `oeis.md`: the OEIS forbids AI-generated submissions, so the packet never drafts an entry.
  It provides raw data only.
- `data/`: the certificate, check report, manifest, `.zenodo.json` and `CITATION.cff`.
- `CHECKLIST.md`: the gates that passed, the novelty verdict, a venue recommendation, and
  the steps only a human can take:
  - read the thread
  - re-run the checker
  - decide authorship (AI tools cannot be authors)
  - deposit the data
  - post the forum comment
  - optionally submit to arXiv or a journal

For a frontier extension like #458, the realistic venue is a comment on the problem's
forum thread with code and data deposited. A short arXiv note is optional.

## Tests

```bash
pytest -q                    # ~130 tests, under a minute
pytest -q -m network         # live database/forum checks
ERDOS_ENGINE_NO_NATIVE=1 pytest -q tests/test_nt.py   # pure-Python fallback
```

## Layout

```
src/erdos_engine/
  native/primekit.c     C kernel: Montgomery arithmetic, primality, #458 square scan
  nt.py                 independent pure-Python number theory
  catalog.py            problem database, problem pages, forum threads
  literature.py         frontier-claim extraction, OEIS/arXiv lookups, novelty gate
  solvers/              one module per problem (+ base classes)
  certify.py            run directories and manifests
  publish/              packet builder, LaTeX templates, bibliography
  cli.py
tests/                  unit, property-based, cross-implementation, tamper/mutation, end-to-end
results/                runs produced in this repository
```

## AI use

This software was written with an AI coding assistant (Claude, Anthropic). Anyone who
publishes results produced with it should disclose that, review the code, and re-run
the checks themselves.
