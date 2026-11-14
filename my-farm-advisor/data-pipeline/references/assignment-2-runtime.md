# Assignment 2 runtime location

This branch (`assignment-2`) uses a separate runtime root so that the
Assignment 1 runtime and its data stay untouched.

## Paths

| Item | Path |
| --- | --- |
| Skill checkout (this branch) | `/home/coder/work/mfask-worktree/assignment-2` |
| Runtime root (Assignment 2) | `/home/coder/my-farm-advisor-runtime-a2` |
| Runtime base | `/home/coder/my-farm-advisor-runtime-a2/data-pipeline` |
| Runtime source copy | `/home/coder/my-farm-advisor-runtime-a2/data-pipeline/src` |
| Runtime venv | `/home/coder/my-farm-advisor-runtime-a2/data-pipeline/.venv` |
| Assignment 1 runtime (reference, do not modify) | `/home/coder/my-farm-advisor-runtime` |

The Assignment 2 runtime was copied from the Assignment 1 runtime as a full
copy (no hard links) so that writes in Assignment 2 cannot alter Assignment 1
data. The copied venv shebangs and activation scripts were rewritten to the new
venv path.

## Per-shell setup

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime-a2
export DATA_PIPELINE_VENV_DIR="${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv"
```

Do not change the persisted default in
`${XDG_CONFIG_HOME:-$HOME/.config}/environment.d/60-my-farm-advisor.conf`; it
still points at the Assignment 1 runtime. Export the Assignment 2 root
explicitly in each shell that runs pipeline commands.

## Runtime source refresh

`${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.my-farm-advisor-source.json` points
at `/home/coder/work/mfask-worktree/assignment-2/my-farm-advisor`. When runtime
scripts change on this branch, refresh the runtime source from the checkout:

```bash
cd /home/coder/work/mfask-worktree/assignment-2/my-farm-advisor/data-pipeline
DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime-a2 \
  ./scripts/install.sh --non-interactive --force-refresh --persist none
```

## Data handling

- Generated outputs, downloaded payloads, reports, logs, and manifests stay
  under `/home/coder/my-farm-advisor-runtime-a2/data-pipeline`.
- Never commit runtime data, raw downloads, or geodata payloads to GitHub. The
  repository `.gitignore` already excludes `data/`, `.cache/`, and generated
  output folders.
