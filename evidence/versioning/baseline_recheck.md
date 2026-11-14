# Baseline reproduction check (PASSED)

Version `9ade7848e5dc`, replayed on the final code by `scripts/recheck_baseline.py`.

22 behaviour fields compared with the frozen scorecard: all identical.
LLM tokens: 1,519,237 frozen, 1,520,249 now. The stand-in's token count moves when agent requests carry more facts. It is not a behaviour field.
Leakage perturbation test: passed.
