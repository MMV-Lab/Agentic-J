#!/bin/bash
# TrackMate micromamba shim
# TrackMate v8 hardcodes /usr/local/opt/micromamba/bin/micromamba.
# This shim forwards calls to conda, routing by the requested env name:
#   cpsam model in args             → cellpose4  (forced — cpsam requires cellpose 4.x SAM)
#   '-n base' or no env arg         → cellpose   (TrackMate-Cellpose 3.x default)
#   '-n omnipose'                   → cellpose   (omnipose 1.x shares the cellpose 3.x env)
#   '-n cellpose4'                  → cellpose4  (TrackMate Cellpose-SAM, cellpose 4.x)
#   '-n stardist'                   → stardist   (TrackMate-StarDist)
#   any other named env             → that env   (forward as-is)

CMD="${1:-}"
if [ "$CMD" = "run" ]; then
    shift
    # Extract the -n <envname> argument; TrackMate-Cellpose defaults to '-n base'
    ENV_NAME=""
    ARGS=()
    while [ $# -gt 0 ]; do
        if [ "$1" = "-n" ] && [ $# -gt 1 ]; then
            ENV_NAME="$2"
            shift 2
        else
            ARGS+=("$1")
            shift
        fi
    done
    # Force cellpose4 when cpsam model is requested — cellpose 3.x cannot run it
    for arg in "${ARGS[@]}"; do
        if [ "$arg" = "cpsam" ]; then
            echo "[shim] cpsam detected → routing to cellpose4 env" >&2
            exec /opt/conda/bin/conda run --prefix /opt/conda/envs/cellpose4 "${ARGS[@]}"
        fi
    done
    # Route: empty or 'base' or 'omnipose' → cellpose; all other named envs → use as-is
    if [ -z "$ENV_NAME" ] || [ "$ENV_NAME" = "base" ] || [ "$ENV_NAME" = "omnipose" ]; then
        echo "[shim] env='${ENV_NAME:-<none>}' → routing to cellpose env" >&2
        exec /opt/conda/bin/conda run --prefix /opt/conda/envs/cellpose "${ARGS[@]}"
    else
        echo "[shim] env='$ENV_NAME' → routing to $ENV_NAME env" >&2
        exec /opt/conda/bin/conda run --prefix /opt/conda/envs/"$ENV_NAME" "${ARGS[@]}"
    fi
elif [ "$CMD" = "env" ] && [ "${2:-}" = "list" ]; then
    # Emit micromamba-style env list output — TrackMate-Cellpose parses this format.
    # conda env list format differs (uses '#' comment headers) and may not be parsed.
    # We emit the header micromamba uses, then list envs from conda, then add the
    # virtual 'omnipose' entry so it appears in the TrackMate dropdown.
    printf "  Name                  Active  Path\n"
    printf -- "─%.0s" {1..62}; printf "\n"
    /opt/conda/bin/conda env list --no-pip 2>/dev/null | grep -v "^#" | grep -v "^$" | while read -r name rest; do
        active=" "
        if echo "$rest" | grep -q "\*"; then
            active="*"
            path=$(echo "$rest" | sed 's/\*.*//' | tr -d ' ')
        else
            path=$(echo "$rest" | tr -d ' ')
        fi
        printf "  %-22s%-8s%s\n" "$name" "$active" "$path"
    done
    printf "  %-22s%-8s%s\n" "omnipose" " " "/opt/conda/envs/cellpose"
else
    exec /opt/conda/bin/conda "$@"
fi
