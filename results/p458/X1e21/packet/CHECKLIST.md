# Publication checklist -- Erdős Problem #458

Generated 2026-10-06 by erdos-engine 0.1.0.

## Automated gates (all passed, or this file would not exist)
- [x] Run manifest verified (no file modified since the run)
- [x] Independent check passed (`p458-independent-python`)
- [x] Outcome is conclusive: `verified_to_bound`

## Novelty
Verdict: **new-frontier** -- Our bound 1e+21 exceeds the largest claim found (1e+20).
Prior claim used: 1e+20 from bhowerton, erdosproblems.com forum, 12 Jun 2026; that verification relies on prime-gap records above 4e18

## Recommended venue
Extends the published computational frontier. Standard venue: a comment on the problem's erdosproblems.com thread with code and data deposited (GitHub + Zenodo DOI). A short arXiv note is optional; journals (e.g. Mathematics of Computation, Experimental Mathematics) generally want more than a range extension unless the method is new.

## Steps only a human can do
1. Read the whole forum thread https://www.erdosproblems.com/forum/thread/458 and the
   problem page; confirm the novelty verdict above (it comes from automatic text extraction).
2. Read the code that produced the certificate and re-run the checker yourself
   (`erdos-engine check <run dir> --thorough`), ideally on different hardware.
3. Decide authorship. AI tools cannot be authors (arXiv, most journals); keep the AI-use
   disclosure in the paper and in any forum post.
4. Fill in the author block and every `TODO(human)` in `paper/main.tex`; rebuild the PDF.
5. Push the code and run directory to a public repository; deposit `data/` on Zenodo
   (metadata in `data/.zenodo.json`) to get a DOI; put the URL and DOI in the paper and the
   forum comment.
6. Post `forum_comment.md` (edited) on the problem's thread.
7. Optional, per the venue advice: submit `paper/arxiv-submission.tar.gz` to arXiv (first-time
   submitters may need an endorsement for the category), then a journal.
8. Database (`database_update.md`) and OEIS (`oeis.md`): follow the notes; OEIS entries must be
   written by a human.

## Warnings
- author block contains placeholders
- novelty verdict comes from automatic extraction; a human must confirm it
