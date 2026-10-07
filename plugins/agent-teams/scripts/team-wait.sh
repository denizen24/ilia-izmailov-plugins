#!/usr/bin/env bash
# team-wait.sh — участник ждёт письмо в своём почтовом ящике, не заканчивая работу вслепую.
#
#   team-wait.sh <run-dir> <моё имя> [--kind VERDICT] [--task <id>] [--interval <сек>] [--max <сек>]
#
# Запускается участником в фоне (run_in_background: true) сразу после запроса,
# на который нужен ответ: кодер — после REVIEW (`--kind VERDICT`) и после QUESTION /
# ESCALATION / STUCK, вернувшегося `queued` (`--kind ANSWER`, с 0.17.0: ведущий кладёт
# ответ файлом до сообщения). KIND любой — сверяется со строкой `kind:` письма без
# учёта регистра; без --kind подходит любое письмо. Завершается, как только в
# <run-dir>/mail/<моё имя>/ появилось ещё не прочитанное письмо нужного вида и
# задачи: печатает путь и текст письма и отмечает его прочитанным в
# mail/<моё имя>/.seen. Завершение фоновой задачи будит участника — даже если
# SendMessage с тем же ответом вернулся `queued` и потерялся (прогон 121-374:
# ~12 ручных пересылок; прогон fix-391-388 с ожиданием файла — ни одной).
#
# Если ответ уже пришёл сообщением раньше файла — ничего страшного: ожидание
# выйдет, когда файл ляжет, и участник увидит, что это тот же ответ.
# По --max (по умолчанию 3600 с) печатает TIMEOUT: тогда спросить ведущего.
# Ожидание стоит ноль токенов: между проверками спит sleep, а не модель.
set -u
run="${1:-}"; me="${2:-}"; shift 2 2>/dev/null || { echo "team-wait: run-dir и имя" >&2; exit 2; }
[ -d "$run" ] && [ -n "$me" ] || { echo "team-wait: нужен каталог прогона и имя участника" >&2; exit 2; }
kind=""; task=""; interval=15; max=3600
while [ $# -gt 0 ]; do
  case "$1" in
    --kind) kind=$(printf '%s' "$2" | tr '[:lower:]' '[:upper:]'); shift 2 ;;
    --task) task="$2"; shift 2 ;;
    --interval) interval="$2"; shift 2 ;;
    --max) max="$2"; shift 2 ;;
    *) echo "team-wait: неизвестный аргумент $1" >&2; exit 2 ;;
  esac
done
box="$(cd "$run" && pwd)/mail/$me"
mkdir -p "$box"; touch "$box/.seen"
started=$(date +%s)
while :; do
  for f in "$box"/*.md; do
    [ -e "$f" ] || continue
    name=$(basename "$f")
    grep -qxF "$name" "$box/.seen" && continue
    head=$(sed -n '1,/^$/p' "$f")
    if [ -n "$kind" ]; then
      printf '%s\n' "$head" | grep -qi "^kind:[[:space:]]*$kind[[:space:]]*$" || continue
    fi
    if [ -n "$task" ]; then
      printf '%s\n' "$head" | grep -q "^task:[[:space:]]*#\?$task[[:space:]]*$" || continue
    fi
    echo "$name" >> "$box/.seen"
    echo "MAIL: $f"
    cat "$f"
    exit 0
  done
  if [ $(( $(date +%s) - started )) -ge "$max" ]; then
    echo "TIMEOUT: за ${max} с в $box нет письма${kind:+ $kind}${task:+ по задаче $task} — спросите ведущего"
    exit 0
  fi
  sleep "$interval"
done
