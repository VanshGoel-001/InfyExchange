#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

: "${BACKUP_AGE_RECIPIENT:?Set BACKUP_AGE_RECIPIENT to the age public recipient}"
: "${BACKUP_REMOTE:?Set BACKUP_REMOTE to a dedicated rclone remote path}"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/infyexchange}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

if [[ ! "$BACKUP_RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
	echo "BACKUP_RETENTION_DAYS must be a non-negative integer" >&2
	exit 2
fi

for command_name in age docker rclone; do
	if ! command -v "$command_name" >/dev/null 2>&1; then
		echo "Required command not found: $command_name" >&2
		exit 127
	fi
done

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
compose_dir="$(cd -- "$script_dir/.." && pwd)"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
filename="infyexchange-${timestamp}.dump.age"
temporary_dir="$(mktemp -d "${TMPDIR:-/tmp}/infyexchange-backup.XXXXXX")"
trap 'rm -rf -- "$temporary_dir"' EXIT

mkdir -p -- "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

(
	cd "$compose_dir"
	docker compose --profile prod exec -T postgres \
		sh -c 'exec pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"'
) | age -r "$BACKUP_AGE_RECIPIENT" -o "$temporary_dir/$filename"

rclone copyto "$temporary_dir/$filename" "${BACKUP_REMOTE%/}/$filename"
install -m 600 "$temporary_dir/$filename" "$BACKUP_DIR/$filename"

find "$BACKUP_DIR" -type f -name 'infyexchange-*.dump.age' \
	-mtime "+$BACKUP_RETENTION_DAYS" -delete
rclone delete "$BACKUP_REMOTE" --min-age "${BACKUP_RETENTION_DAYS}d" \
	--include 'infyexchange-*.dump.age'

printf 'Encrypted database backup uploaded: %s/%s\n' "${BACKUP_REMOTE%/}" "$filename"