"""Shared semantic patch comparison utilities."""

from __future__ import annotations

import difflib
from typing import Dict, List


def _extract_modifications(patch: str) -> List[Dict[str, List[str]]]:
    """Extract file-level additions/deletions from a unified diff patch."""
    modifications: List[Dict[str, List[str]]] = []
    current_file = None
    additions: List[str] = []
    deletions: List[str] = []

    for line in patch.split("\n"):
        if line.startswith("--- a/") or line.startswith("--- "):
            if current_file and (additions or deletions):
                modifications.append(
                    {
                        "file": current_file,
                        "additions": additions.copy(),
                        "deletions": deletions.copy(),
                    }
                )
                additions = []
                deletions = []
            parts = line.split()
            if len(parts) >= 2:
                current_file = parts[1].replace("a/", "").replace("b/", "")
        elif line.startswith("+++ b/") or line.startswith("+++ "):
            parts = line.split()
            if len(parts) >= 2:
                current_file = parts[1].replace("a/", "").replace("b/", "")
        elif line.startswith("+") and not line.startswith("+++"):
            additions.append(line[1:].strip())
        elif line.startswith("-") and not line.startswith("---"):
            deletions.append(line[1:].strip())

    if current_file and (additions or deletions):
        modifications.append(
            {
                "file": current_file,
                "additions": additions.copy(),
                "deletions": deletions.copy(),
            }
        )

    return modifications


def compute_patch_metrics(generated: str, expected: str) -> Dict[str, object]:
    """
    Compute patch-level semantic overlap metrics.

    Returns a dict with precision/recall/F1 and file overlap.
    """
    gen_mods = _extract_modifications(generated or "")
    exp_mods = _extract_modifications(expected or "")

    gen_files = {m["file"] for m in gen_mods}
    exp_files = {m["file"] for m in exp_mods}
    files_correct = len(gen_files & exp_files) / max(len(exp_files), 1)

    gen_additions = set()
    gen_deletions = set()
    exp_additions = set()
    exp_deletions = set()

    for m in gen_mods:
        gen_additions.update(m["additions"])
        gen_deletions.update(m["deletions"])

    for m in exp_mods:
        exp_additions.update(m["additions"])
        exp_deletions.update(m["deletions"])

    add_overlap = len(gen_additions & exp_additions)
    del_overlap = len(gen_deletions & exp_deletions)

    total_exp = len(exp_additions) + len(exp_deletions)
    total_gen = len(gen_additions) + len(gen_deletions)
    total_overlap = add_overlap + del_overlap

    recall = total_overlap / total_exp if total_exp > 0 else 0.0
    precision = total_overlap / total_gen if total_gen > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    # Fuzzy recall based on line-level similarity
    all_gen = list(gen_additions) + list(gen_deletions)
    all_exp = list(exp_additions) + list(exp_deletions)
    fuzzy_matches = 0.0
    for exp_line in all_exp:
        if exp_line in all_gen:
            fuzzy_matches += 1.0
        else:
            matches = difflib.get_close_matches(exp_line, all_gen, n=1, cutoff=0.8)
            if matches:
                fuzzy_matches += 0.8
    fuzzy_recall = fuzzy_matches / max(len(all_exp), 1)

    return {
        "files_correct": files_correct,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "fuzzy_recall": fuzzy_recall,
        "generated_files": list(gen_files),
        "expected_files": list(exp_files),
        "gen_additions": len(gen_additions),
        "exp_additions": len(exp_additions),
        "gen_deletions": len(gen_deletions),
        "exp_deletions": len(exp_deletions),
    }


def semantic_match_score(generated: str, expected: str) -> float:
    """Return the F1 score for semantic patch comparison."""
    return float(compute_patch_metrics(generated, expected)["f1_score"])
