# SWE-Bench-A2A: A Framework for Contamination-Resistant and Process-Aware Agent Evaluation

[![Paper](https://img.shields.io/badge/Paper-PDF-red)](paper/a2a_swebench.pdf)
[![AgentBeats](https://img.shields.io/badge/AgentBeats-Integration-blue)](https://agentbeats.dev/ManishMuttreja1/a2a-swe-bench)

An evaluation framework for software engineering agents that quantifies **contamination** and **robustness gaps** in SWE-bench benchmarks.

## Key Results

| Finding | Metric | Implication |
|---------|--------|-------------|
| **Contamination Gap** | 20.2% → 17.2% (-2.9%) | ~14% relative overstatement |
| **Robustness Gap** | 60% semantic → 51.3% robust | ~15% relative overstatement |
| **Proven Memorization** | sklearn-14141: 100% → 0% | Some "perfect" scores are recall, not reasoning |
| **Mutation Resilience** | 22% | Patches match text but don't generalize |

**Conclusion**: Standard SWE-bench metrics likely overstate true engineering capability by **14-15%**.

## Our Contributions

1. **Framework**: SWE-Bench-A2A implementing A2A protocol with reproduction gates and process scoring
2. **Contamination Detection**: Retro-holdout testing on 100 instances (7 with >50% drops)
3. **Robustness Analysis**: Adversarial testing revealing 51.3% overall robustness vs 60% semantic
4. **Cross-Provider Evaluation**: GPT-4o, GPT-5.2, Claude Sonnet 4.5, Opus 4.1, Haiku (100 instances each)
5. **Open Infrastructure**: Dockerfiles, CI scaffolding, anti-contamination pipeline

## Quick Start

```bash
# Clone
git clone https://github.com/ManishMuttreja1/A2A-SWE-Bench.git
cd A2A-SWE-Bench

# Install
pip install -r requirements.txt

# Run Green Agent (assessor)
python start_green_agent.py

# Run Purple Agent (solver) - in another terminal
OPENAI_API_KEY=sk-... python start_purple_agent.py

# Or run benchmark directly
python test_gpt4o_a2a_full.py --tasks 10
```

## Cross-Provider Results

⚠️ **METHODOLOGY WARNING**: Results below use non-uniform task selection. GPT-4o was tested on the 100 **easiest** tasks (sorted by patch size, avg 477 chars), while other models used random sampling (avg 1538 chars—3.2× harder).

**Fair Comparison (same 22 tasks):**
| Model | Score |
|-------|-------|
| **GPT-5.2** | **26.5%** |
| GPT-4o | 19.8% |

**Full Results (non-comparable due to different task sets):**
| Model | Avg Semantic Match | Task Set | Notes |
|-------|-------------------|----------|-------|
| Claude Sonnet 4.5 | 27.7% | Random | Anthropic |
| GPT-4o | 19.6% | **Easy (sorted)** | 4 runs avg |
| Claude Opus 4.1 | 18.8% | Random | Anthropic |
| GPT-5.2 | 18.5% | Random | Likely underestimated |
| Claude 3 Haiku | 18.5% | Random | Anthropic |

## Anti-Contamination Testing

The retro-holdout pipeline applies semantic-preserving mutations to detect memorization:

```bash
# Run anti-contamination test
python test_anti_contamination.py --tasks 100 --model gpt-4o
```

**Results** (100 instances):
- Verified avg: 20.2% → Mutated avg: 17.2%
- 7 instances showed >50% contamination (complete memorization)
- Key case: `sklearn-14141` dropped 100% → 0%

## Adversarial Testing

Tests patch robustness beyond repository test suites:

```bash
# Run adversarial test
python test_adversarial.py --tasks 10 --model gpt-5.2
```

**Results** (10 instances):
| Test Type | Score |
|-----------|-------|
| Fuzz Testing | 97.7% |
| Adversarial Edge Cases | 44.0% |
| Mutation Testing | **22.0%** |
| Overall Robustness | 51.3% |

The low mutation score (22%) proves patches are **brittle**—they match expected text but break when code is slightly altered.

## Architecture

```
┌─────────────────┐         ┌─────────────────┐
│   Green Agent   │◄───────►│  Purple Agent   │
│   (Assessor)    │  A2A    │   (Solver)      │
├─────────────────┤         ├─────────────────┤
│ • Task dispatch │         │ • LLM solver    │
│ • Verification  │         │ • Patch gen     │
│ • Scoring       │         │ • Multi-provider│
└────────┬────────┘         └─────────────────┘
         │
         ▼
┌─────────────────┐
│ Anti-Contamination │
├─────────────────┤
│ • Retro-holdout │
│ • Adversarial   │
│ • Fresh harvest │
└─────────────────┘
```

## Project Structure

```
swebench-a2a/
├── src/
│   ├── a2a/                 # A2A protocol implementation
│   ├── green_agent/         # Assessor agent
│   ├── purple_agent/        # Solver agent
│   ├── anti_contamination/  # Retro-holdout pipeline
│   ├── adversarial/         # Fuzz, edge case, mutation testing
│   ├── scoring/             # Multi-dimensional metrics
│   └── trajectory/          # Action logging
├── paper/
│   ├── a2a_swebench.tex     # Paper source
│   └── a2a_swebench.pdf     # Compiled paper
├── leaderboard/             # AgentBeats config
├── test_*.py                # Benchmark scripts
├── Dockerfile.green         # Green Agent container
├── Dockerfile.purple        # Purple Agent container
└── scenario.toml            # AgentBeats scenario config
```

## AgentBeats Integration

This framework integrates with [AgentBeats](https://agentbeats.dev/) for standardized evaluation:

```bash
# Generate Docker Compose from scenario
python generate_compose.py --scenario scenario.toml

# Run assessment
docker compose up
```

See `.github/workflows/assessment.yml` for CI automation.

## Limitations

- **Semantic similarity ≠ execution pass/fail**: Metrics are textual, not execution-based
- **Process scoring not computed**: Defined mathematically but not implemented in experiments
- **Single-run variance**: 7-18% variance observed; comparisons are statistically fragile
- **Adversarial sample size**: Only 10 instances tested

## Citation

```bibtex
@article{muttreja2026swebench-a2a,
  title={SWE-Bench-A2A: A Framework for Contamination-Resistant and Process-Aware Agent Evaluation},
  author={Muttreja, Manish},
  journal={arXiv preprint},
  year={2026}
}
```

## License

MIT License - See LICENSE file for details.
