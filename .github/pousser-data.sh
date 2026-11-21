#!/usr/bin/env bash
# Enregistre data/ dans le dépôt, même si un autre workflow a poussé entre-temps.
#   pousser-data.sh "message de commit" [fichier à imposer…]
# En cas de conflit (deux workflows ont modifié le même fichier), on repart de la version
# distante et on n'impose que les fichiers donnés (par défaut : tous ceux modifiés ici).
# 3 essais, avec une attente croissante.
set -u
message="$1"; shift
git config user.name "veille-bot"
git config user.email "veille-bot@users.noreply.github.com"
git add data/
git diff --cached --quiet && { echo "data/ : rien de nouveau"; exit 0; }
git commit -q -m "$message"

if [ "$#" -gt 0 ]; then imposes="$*"; else imposes=$(git diff --name-only HEAD~1 HEAD -- data/); fi
garde="${RUNNER_TEMP:-/tmp}/data-a-garder"
rm -rf "$garde"
for f in $imposes; do
  [ -f "$f" ] && mkdir -p "$garde/$(dirname "$f")" && cp "$f" "$garde/$f"
done

for essai in 1 2 3; do
  if git pull --rebase -q; then
    git push -q && { echo "data/ enregistré (essai $essai)"; exit 0; }
    echo "push refusé (quelqu'un a poussé entre-temps), nouvel essai"
  else
    echo "conflit avec un autre enregistrement : version distante + nos fichiers ($imposes)"
    git rebase --abort
    git reset -q --hard origin/main
    for f in $imposes; do
      [ -f "$garde/$f" ] && mkdir -p "$(dirname "$f")" && cp "$garde/$f" "$f"
    done
    git add data/
    git diff --cached --quiet || git commit -q -m "$message"
  fi
  sleep $((essai * 15))
done
echo "data/ non enregistré après 3 essais" >&2
exit 1
