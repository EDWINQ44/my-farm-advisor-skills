# Local Instructions

## Purpose

This folder owns the cross-producer comparison workflow for the assignment-2
demo farms: field-area comparisons, growing-season climate, CDL composition
and transitions, and a static three-panel boundary map.

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly
asks for a broader skill change. The executable lives in
`../../../data-pipeline/src/scripts/eda/eda_farm_comparison.py` because the
runtime contract requires scripts to run from the runtime source copy. Do not
change parent `SKILL.md`, sibling EDA workflows, or root policy from a
subskill task unless explicitly requested.

## Read nearby docs first

Read `GUIDE.md` first, then `references/assignment-2-data-contract.md`. If
routing context is needed, read `../INDEX.md` and `../../SKILL.md`. For the
generated data and runtime paths, read
`../../../data-pipeline/AGENTS.md`.

## Non-goals

No soil analysis, no interactive dashboards, no HTML producer maps, and no
final PDF/HTML report assembly in this workflow. Do not add per-field
irrigation claims: the dataset has no field-level irrigation evidence.

## Local validation

Run `./scripts/validate.sh` from the repository root after structural changes.
After changing the figure script, refresh the runtime source and run the
workflow against the assignment-2 runtime; confirm the manifest checks pass and
review all seven figures before shipping.

## Local-delta-only reminder

This nested AGENTS.md only records instructions that differ from the parent or
root files. Do not duplicate root-wide asset, vendor, or validation policy here
except this pointer to `../../../AGENTS.md`.
