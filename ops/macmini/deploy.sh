#!/bin/bash
set -Eeuo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/env.sh"
. "$HERE/lib.sh"
mkdir -p "$SHARED" "$APP_ROOT/releases" "$APP_ROOT/logs"
preflight || exit 1
acquire_lock || exit 0
trap 'log error "\"line\":$LINENO"' ERR

write_state() { # phase sha previous snapshot (all paths may contain spaces)
    printf '%s %s %s %s\n' "$1" "$sha" "${previous:--}" "${snapshot:--}" > "$SHARED/deploy-state.tmp"
    mv -f "$SHARED/deploy-state.tmp" "$SHARED/deploy-state"
}
finish_success() {
    local last ops_outdated=false
    last="$(tail -n 1 "$HISTORY" 2>/dev/null | awk '{print $1}' || true)"
    if [[ "$last" != "$sha" ]]; then
        printf '%s %s\n' "$sha" "$snapshot" >> "$HISTORY" || return 1
    fi
    diff -rq "$HERE" "$APP_ROOT/releases/$sha/ops/macmini" >/dev/null 2>&1 || ops_outdated=true
    log deployed "\"ops_outdated\":$ops_outdated" || return 1
    rm -f "$SHARED/deploy-state" || return 1
    prune_releases
}
rollback_candidate() {
    printf '%s\n' "$sha" > "$FAILED"
    if [[ -z "$previous" || ! -d "$APP_ROOT/releases/$previous" ]]; then
        log unhealthy '"rolled_back_to":null'
        rm -f "$SHARED/deploy-state"
        return 1
    fi
    write_state rolling-back
    restart_services stop || { log error '"reason":"rollback stop failed"'; return 1; }
    restore_sessions "$snapshot" || { log error '"reason":"snapshot restore failed"'; return 1; }
    switch_to "$previous" || { log error '"reason":"rollback switch failed"'; return 1; }
    restart_services start || { log error '"reason":"rollback start failed"'; return 1; }
    if wait_healthy "$DCX_HEALTH_TIMEOUT" "$previous"; then
        rm -rf "$APP_ROOT/releases/$sha"
        log unhealthy "$(python3.12 -c 'import json,sys; print(json.dumps(dict(rolled_back_to=sys.argv[1],snapshot=sys.argv[2])))' "$previous" "$snapshot")"
    else
        log unhealthy-both "\"rolled_back_to\":\"$previous\""
    fi
    rm -f "$SHARED/deploy-state"
    return 1
}
verify_candidate() {
    if wait_healthy "$DCX_HEALTH_TIMEOUT" "$sha"; then
        finish_success || { log error '"reason":"deployment finalization failed"'; return 1; }
    else
        rollback_candidate
    fi
}

# Recovery precedes the up-to-date short circuit and any fetch/CI request.
if [[ -s "$SHARED/deploy-state" ]]; then
    IFS=' ' read -r phase sha previous snapshot < "$SHARED/deploy-state"
    [[ "$previous" != - ]] || previous=""
    if [[ "${DEPLOY_DRY_RUN:-0}" == 1 ]]; then
        log error '"dry_run":true,"reason":"recovery pending"'
        exit 0
    fi
    case "$phase" in
        preparing)
            # No data/symlink changes were authorized yet; resume old services.
            restart_services start
            rm -f "$SHARED/deploy-state"
            ;;
        switching)
            if [[ "$(current_sha)" != "$sha" ]]; then
                restart_services stop
                switch_to "$sha"
            fi
            restart_services start
            if verify_candidate; then exit 0; else exit 1; fi ;;
        rolling-back)
            if rollback_candidate; then exit 0; else exit 1; fi ;;
        *) log error '"reason":"invalid deploy-state"'; exit 1 ;;
    esac
fi
if [[ ! -d "$APP_ROOT/repo/.git" ]]; then
    git clone --quiet "$DCX_REPO_URL" "$APP_ROOT/repo"
fi
git -C "$APP_ROOT/repo" fetch --quiet origin main
sha="$(git -C "$APP_ROOT/repo" rev-parse --verify "${DEPLOY_SHA:-origin/main}^{commit}")"
if [[ "$sha" == "$(current_sha)" ]]; then
    if [[ "${DEPLOY_DRY_RUN:-0}" == 1 ]]; then log up-to-date; fi
    exit 0
fi
if [[ "$sha" == "$(cat "$FAILED" 2>/dev/null || true)" ]]; then
    if [[ "${DEPLOY_DRY_RUN:-0}" == 1 ]]; then log known-failed; fi
    exit 0
fi
ci="$(ci_status "$sha")"
case "$ci" in
    success) ;;
    failed:*)
        key="$sha $ci"
        if [[ "$key" != "$(cat "$SHARED/last-ci-failure" 2>/dev/null || true)" ]]; then
            log ci-failed "\"ci\":\"$ci\""
            [[ "${DEPLOY_DRY_RUN:-0}" == 1 ]] || printf '%s\n' "$key" > "$SHARED/last-ci-failure"
        fi
        exit 0 ;;
    pending)
        since="$(awk -v s="$sha" '$1 == s {print $2}' "$SHARED/ci-pending-since" 2>/dev/null || true)"
        if [[ "${DEPLOY_DRY_RUN:-0}" == 1 ]]; then log ci-pending; exit 0; fi
        case "$since" in ''|*[!0-9]*) since="$(epoch_now)"; printf '%s %s\n' "$sha" "$since" > "$SHARED/ci-pending-since" ;; esac
        if (( $(epoch_now) - since > 1800 )) && [[ ! -f "$SHARED/ci-stuck-$sha" ]]; then
            log ci-stuck
            touch "$SHARED/ci-stuck-$sha"
        fi
        exit 0 ;;
    *) log ci-unknown; exit 0 ;;
esac
if [[ "${DEPLOY_DRY_RUN:-0}" == 1 ]]; then
    # Allowed decision vocabulary, with an explicit dry-run flag.
    log deployed '"dry_run":true'
    exit 0
fi
if ! build_release "$sha"; then
    printf '%s\n' "$sha" > "$FAILED"
    log build-failed
    exit 1
fi
previous="$(current_sha)"
snapshot=-
write_state preparing
restart_services stop
snapshot="$(snapshot_sessions "$sha")"
write_state switching
switch_to "$sha"
restart_services start
if verify_candidate; then exit 0; else exit 1; fi
