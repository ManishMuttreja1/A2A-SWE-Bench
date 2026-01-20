SWE-Bench-A2A Fix Checklist
===========================

1) Unify semantic patch metric across all benchmarks
   - Add shared metric helper in src/scoring/semantic_patch.py
   - Update GPT-4o, Claude, anti-contamination scripts to use it
   - Regenerate result JSONs with consistent metric field(s)

2) Make anti-contamination pipeline real and reproducible
   - Use AntiContaminationPipeline in the anti-contamination runner
   - Ensure original vs mutated repo paths are distinct
   - Fix OpenAI parameter usage for the configured model
   - Rerun 100-instance verified vs mutated and save metadata

3) Align adversarial testing with execution-based verification
   - Wire AdversarialEvaluator into container verification
   - If heuristics remain, relabel results as heuristic-only
   - Rerun adversarial eval and save summary

4) Reproduction gate + experiment mapping
   - Decide: enforce gate in reported experiments or explicitly disable
   - Ensure Purple agent emits reproduction_script when gate is on
   - Add metadata to results: gate_enabled, heuristics_allowed, metric

5) Paper and README reconciliation
   - Update tables/claims to match regenerated results
   - Reference exact result files + experiment IDs
